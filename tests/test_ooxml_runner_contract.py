"""Shared runner contract: identity, plan binding, adapter loading, reports.

These tests never start Docker. They cover what the runner refuses and what it
accepts, which is where a false pass would come from.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from runner_fixtures import (
    ADAPTER_SOURCE,
    REPO,
    RUNNER_COMMIT,
    expected_for,
    make_plan,
    make_repo,
    passing_report,
)

from ooxml_runner import adapter as adapters
from ooxml_runner import cli, docker, identity, snapshot
from ooxml_runner import plan as plan_module
from ooxml_runner import report as report_module


def describe(tmp_path, repo, plan, **kwargs):
    return cli.describe_repository(root=tmp_path, repo=REPO, commit="HEAD",
                                   runner_commit=RUNNER_COMMIT, plan=plan, **kwargs)


# --- identity -----------------------------------------------------------------

def test_runner_refuses_a_commit_it_is_not_running_as(tmp_path):
    repo = make_repo(tmp_path)
    with pytest.raises(identity.IdentityError):
        cli.describe_repository(root=tmp_path, repo=REPO, commit="HEAD",
                                runner_commit="0" * 40, plan=make_plan(tmp_path, repo))


def test_runner_refuses_a_short_pinned_commit(tmp_path):
    repo = make_repo(tmp_path)
    with pytest.raises(identity.IdentityError):
        cli.describe_repository(root=tmp_path, repo=REPO, commit="HEAD",
                                runner_commit="abc123", plan=make_plan(tmp_path, repo))


def test_identity_ignores_a_git_dir_inherited_from_a_git_hook(tmp_path, monkeypatch):
    """A pre-push hook exports GIT_DIR; the runner must still read its own checkout."""
    other = make_repo(tmp_path / "other")
    snapshot.git(other, "commit", "--quiet", "--allow-empty", "-m", "a different repository")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    observed = identity.identity()
    assert observed["commit"] == snapshot.git(Path(__file__).resolve().parents[1], "rev-parse", "HEAD")
    assert observed["commit"] != snapshot.git(other, "rev-parse", "HEAD")


def test_describe_starts_nothing(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    monkeypatch.setattr(docker, "execute", pytest.fail)
    monkeypatch.setattr(docker, "cpu_limit", pytest.fail)
    monkeypatch.setattr(snapshot, "credential", pytest.fail)
    payload = describe(tmp_path, repo, make_plan(tmp_path, repo))
    assert payload["executes"] is False
    assert payload["stages"] == ["alpha", "beta"]


# --- plan binding -------------------------------------------------------------

def test_plan_with_error_diagnostics_is_refused(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo, diagnostics=[{"level": "error", "code": "x", "where": "y"}])
    with pytest.raises(plan_module.PlanError, match="blocking diagnostics"):
        describe(tmp_path, repo, plan)


def test_repository_absent_from_the_plan_is_refused(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo, nodes=[{"key": "something-else"}])
    with pytest.raises(plan_module.PlanError, match="not a declared node"):
        describe(tmp_path, repo, plan)


def test_repository_without_a_full_binding_is_refused(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo, full={})
    with pytest.raises(plan_module.PlanError, match="no full-verification binding"):
        describe(tmp_path, repo, plan)


def test_binding_without_an_adapter_is_refused(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo, adapter=None)
    with pytest.raises(plan_module.PlanError, match="declares no adapter"):
        describe(tmp_path, repo, plan)


def test_plan_input_drift_is_refused(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo,
                     inputs=[{"path": _other_repo(tmp_path), "sha256": "b" * 64}])
    with pytest.raises(plan_module.PlanError, match="does not match the workspace"):
        describe(tmp_path, repo, plan)


def test_plan_inputs_absent_from_the_workspace_are_recorded_not_guessed(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo, inputs=["nowhere/missing.json"])
    payload = describe(tmp_path, repo, plan)
    assert payload["plan"]["inputs_reverified"]["verified"] is False
    assert "not present" in payload["plan"]["inputs_reverified"]["reason"]


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
    """A pass says what was proven, and names what was not."""
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo, inputs=[_other_repo(tmp_path), "nowhere/missing.json"])
    payload = describe(tmp_path, repo, plan)["plan"]["inputs_reverified"]

    assert payload["verified"] is True
    assert payload["checked"] == 1
    assert payload["unchecked"] == 1
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
    assert "not present" in payload["reason"]


def test_a_plan_without_an_input_manifest_is_refused(tmp_path):
    """A bare path list cannot be checked input by input, so it is not trusted."""
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo, inputs=[])
    payload = json.loads(Path(plan).read_text())
    payload["inputs"] = [f"{REPO}/ci/environment.json"]
    Path(plan).write_text(json.dumps(payload))

    with pytest.raises(plan_module.PlanError, match="manifest entry is malformed"):
        describe(tmp_path, repo, plan)


# --- adapters -----------------------------------------------------------------

def test_unknown_adapter_module_is_refused(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo, adapter="scripts.ci.nope")
    with pytest.raises(adapters.AdapterError, match="not found"):
        describe(tmp_path, repo, plan)


def test_adapter_missing_protocol_names_is_refused(tmp_path):
    repo = make_repo(tmp_path, adapter="X = 1\n")
    with pytest.raises(adapters.AdapterError, match="missing"):
        describe(tmp_path, repo, make_plan(tmp_path, repo))


def test_adapter_with_no_stages_is_refused(tmp_path):
    repo = make_repo(tmp_path, adapter=ADAPTER_SOURCE.replace("{stages!r}", "[]"))
    with pytest.raises(adapters.AdapterError, match="non-empty stage list"):
        describe(tmp_path, repo, make_plan(tmp_path, repo))


def test_adapter_with_duplicate_stages_is_refused(tmp_path):
    repo = make_repo(tmp_path, adapter=ADAPTER_SOURCE.replace("{stages!r}", "['a', 'a']"))
    with pytest.raises(adapters.AdapterError, match="duplicate stage"):
        describe(tmp_path, repo, make_plan(tmp_path, repo))


def test_a_second_repository_does_not_reuse_the_first_adapter(tmp_path):
    """Loading by dotted name would hand back whichever adapter imported first."""
    first = make_repo(tmp_path / "a", adapter=ADAPTER_SOURCE.replace("{stages!r}", "['alpha']"))
    second = make_repo(tmp_path / "b", adapter=ADAPTER_SOURCE.replace("{stages!r}", "['beta']"))
    assert adapters.describe(adapters.load(first, "scripts.ci.adapter"), first)["stages"] == ["alpha"]
    assert adapters.describe(adapters.load(second, "scripts.ci.adapter"), second)["stages"] == ["beta"]


def test_implemented_stages_must_match_the_declared_order(tmp_path):
    repo = make_repo(tmp_path)
    module = adapters.load(repo, "scripts.ci.adapter")
    module.describe = lambda root: {"stages": ["alpha", "beta"]}
    module.operations = lambda root, reports, config: {"beta": lambda: None, "alpha": lambda: None}
    with pytest.raises(adapters.AdapterError, match="differ from the declared stage contract"):
        adapters.operations(module, repo, tmp_path, {})


# --- report verification ------------------------------------------------------

@pytest.mark.parametrize("fault", ["commit", "runner", "plan", "status", "exit-code",
                                   "missing-stage", "duplicate-stage", "none-stage",
                                   "failed-stage", "not-run-stage", "null-stages"])
def test_report_is_rejected_unless_every_identity_and_stage_matches(tmp_path, fault):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo)
    payload = passing_report(repo, plan)
    if fault == "commit":
        payload["commit"] = "0" * 40
    elif fault == "runner":
        payload["runner"]["commit"] = "0" * 40
    elif fault == "plan":
        payload["plan"]["sha256"] = "0" * 64
    elif fault == "status":
        payload["status"] = "fail"
    elif fault == "exit-code":
        payload["exit_code"] = 1
    elif fault == "missing-stage":
        payload["stages"].pop()
    elif fault == "duplicate-stage":
        payload["stages"].append(payload["stages"][0])
    elif fault == "none-stage":
        payload["stages"][0] = None
    elif fault == "failed-stage":
        payload["stages"][0]["status"] = "fail"
    elif fault == "not-run-stage":
        payload["stages"][0]["status"] = "not_run"
    else:
        payload["stages"] = None
    with pytest.raises(report_module.ReportError):
        report_module.verify_generic(payload, expected_for(repo, plan))


def test_a_valid_report_is_accepted(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo)
    report_module.verify_generic(passing_report(repo, plan), expected_for(repo, plan))


def test_a_report_naming_another_repository_is_rejected(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo)
    payload = passing_report(repo, plan, repository="python-docx")
    with pytest.raises(report_module.ReportError):
        report_module.verify_generic(payload, expected_for(repo, plan))


def test_verify_report_file_rejects_a_report_that_is_not_json(tmp_path):
    path = tmp_path / "report.json"
    path.write_text("{interrupted")
    with pytest.raises(report_module.ReportError):
        report_module.load(tmp_path)


def test_a_report_from_another_plan_is_rejected(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo)
    payload = passing_report(repo, plan)
    other = make_plan(tmp_path, repo, digest="c" * 64)
    with pytest.raises(report_module.ReportError):
        report_module.verify_generic(payload, expected_for(repo, other))


def test_verify_report_file_re_derives_inputs_instead_of_trusting_the_report(tmp_path):
    """A report must not be able to certify its own input digest.

    The adapter compares the report's ``inputs`` against the ones the runner
    re-derived from the snapshot, so a report that carries its own digest is
    refused. Passing the report's own value back in would accept it.
    """
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo)
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(passing_report(repo, plan)))
    cli.verify_report_file(root=tmp_path, repo=REPO, commit="HEAD", runner_commit=RUNNER_COMMIT,
                           plan=plan, report=report_path)

    payload = passing_report(repo, plan)
    payload["inputs"] = {"ci/environment.json": "0" * 64}
    report_path.write_text(json.dumps(payload))
    with pytest.raises(adapters.AdapterError, match="input mismatch"):
        cli.verify_report_file(root=tmp_path, repo=REPO, commit="HEAD",
                               runner_commit=RUNNER_COMMIT, plan=plan, report=report_path)


def test_json_round_trip_preserves_the_verdict(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo)
    payload = passing_report(repo, plan)
    (tmp_path / "report.json").write_text(json.dumps(payload))
    assert report_module.load(tmp_path)["status"] == "pass"