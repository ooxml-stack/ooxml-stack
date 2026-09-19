"""The plan's input manifest: what the runner compares and what it records.

The manifest exists so a consumer holding part of the ecosystem can still check
the parts it has. These cases pin the three outcomes - checked, mismatch,
unchecked - plus the target repository's exclusion, and the accounting that has
to add up across them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from runner_fixtures import REPO, RUNNER_COMMIT, make_plan, make_repo

from ooxml_runner import cli, snapshot
from ooxml_runner import plan as plan_module


def describe(tmp_path, repo, plan):
    return cli.describe_repository(root=tmp_path, repo=REPO, commit="HEAD",
                                   runner_commit=RUNNER_COMMIT, plan=plan)


def test_plan_input_drift_is_refused(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo,
                     inputs=[{"path": _other_repo(tmp_path), "sha256": "b" * 64}])
    with pytest.raises(plan_module.PlanError, match="does not match the workspace"):
        describe(tmp_path, repo, plan)


def test_plan_inputs_absent_from_the_workspace_are_recorded_not_guessed(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo, inputs=["nowhere/missing.json"])
    payload = describe(tmp_path, repo, plan)["plan"]["inputs_reverified"]
    assert payload["verified"] is False
    assert payload["unchecked_paths"] == ["nowhere/missing.json"]
    assert "1 unchecked" in payload["reason"]


def _other_repo(tmp_path, key="python-docx"):
    directory = tmp_path / key
    directory.mkdir(exist_ok=True)
    (directory / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    return f"{key}/pyproject.toml"


def test_a_present_input_that_differs_fails_even_when_others_are_missing(tmp_path):
    """The workspace's completeness must not decide the verdict.

    A partial checkout used to skip every input it could not read - including the
    ones it *could* read and that no longer matched the plan - so the same target
    passed in CI and failed locally. Any input the workspace can supply is now
    checked, and a mismatch fails closed however many others are absent.
    """
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo, inputs=[
        {"path": _other_repo(tmp_path), "sha256": "b" * 64},
        "nowhere/missing.json",
    ])

    with pytest.raises(plan_module.PlanError, match="does not match the workspace"):
        describe(tmp_path, repo, plan)


def test_a_partial_workspace_reports_the_scope_it_could_not_check(tmp_path):
    """A partial workspace is partial evidence, and must not read as complete."""
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo, inputs=[_other_repo(tmp_path), "nowhere/missing.json"])
    payload = describe(tmp_path, repo, plan)["plan"]["inputs_reverified"]

    assert payload["verified"] is False
    assert payload["total"] == 2
    assert payload["checked"] == 1
    assert payload["unchecked"] == 1
    assert payload["unchecked_paths"] == ["nowhere/missing.json"]
    assert "1 of 2 plan inputs checked" in payload["reason"]
    assert "1 unchecked" in payload["reason"]


def test_the_target_repository_inputs_are_not_decided_by_the_worktree(tmp_path):
    """A caller's uncommitted edit must not change the verdict for a commit.

    The target's own configuration is already bound by the commit being verified
    and by the report's input hashes, so the plan's manifest for it is redundant.
    Reading it from the working tree would let a dirty caller fail - or pass - a
    historical commit, which is the defect the pin fix already closed once.
    """
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo,
                     inputs=[{"path": f"{REPO}/ci/environment.json", "sha256": "b" * 64}])
    (tmp_path / REPO / "ci/environment.json").write_text('{"dirty": true}')

    payload = describe(tmp_path, repo, plan)["plan"]["inputs_reverified"]

    assert payload["checked"] == 0
    assert payload["unchecked"] == 0
    assert payload["verified"] is True
    assert payload["excluded"] == [{"path": f"{REPO}/ci/environment.json",
                                    "reason": "target_repository",
                                    "bound_to": snapshot.resolve_commit(repo, "HEAD")}]


def test_every_declared_input_has_an_accounted_place(tmp_path):
    """Counts and paths must add up; nothing may vanish from the statistics."""
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo, inputs=[
        f"{REPO}/ci/environment.json", _other_repo(tmp_path), "nowhere/missing.json",
        _other_repo(tmp_path),  # a duplicate must not be counted twice
    ])
    payload = describe(tmp_path, repo, plan)["plan"]["inputs_reverified"]

    assert payload["total"] == 3
    assert payload["checked"] + payload["unchecked"] + len(payload["excluded"]) == payload["total"]
    assert payload["checked"] == 1
    assert payload["unchecked"] == 1
    assert [entry["path"] for entry in payload["excluded"]] == [f"{REPO}/ci/environment.json"]


def test_a_plan_without_an_input_manifest_is_refused(tmp_path):
    """A bare path list cannot be checked input by input, so it is not trusted."""
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo, inputs=[])
    payload = json.loads(Path(plan).read_text())
    payload["inputs"] = [f"{REPO}/ci/environment.json"]
    Path(plan).write_text(json.dumps(payload))

    with pytest.raises(plan_module.PlanError, match="manifest entry is malformed"):
        describe(tmp_path, repo, plan)


