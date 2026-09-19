"""The plan's verification scope: what a report may claim it checked.

The scope block was written by the runner but never checked by the verifier, so a
report could claim any coverage it liked. These cases start from a valid report
and mutate one field, then go through the real ``verify-report`` entry point.
"""

from __future__ import annotations

import json

import pytest
from runner_fixtures import REPO, RUNNER_COMMIT, make_plan, make_repo, passing_report

from ooxml_runner import cli, report as report_module, snapshot


def _verify(tmp_path, repo, plan, payload):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(payload))
    return cli.verify_report_file(
        root=tmp_path, repo=REPO, commit=snapshot.resolve_commit(repo, "HEAD"),
        runner_commit=RUNNER_COMMIT, plan=plan, report=path,
    )


def _fixture(tmp_path):
    repo = make_repo(tmp_path)
    return repo, make_plan(tmp_path, repo)


def _other_repo(tmp_path, key="python-docx"):
    directory = tmp_path / key
    directory.mkdir(exist_ok=True)
    (directory / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    return f"{key}/pyproject.toml"



def test_verification_rejects_a_forged_scope_that_claims_completeness(tmp_path):
    """``verified`` must mean the applicable scope is complete.

    The scope block was not checked at all, so a report could claim any coverage
    it liked - including a complete pass over a workspace that left inputs
    unread.
    """
    repo, plan = _fixture(tmp_path)
    payload = passing_report(repo, plan)
    payload["plan"]["inputs_reverified"] = {
        "verified": True, "total": 2, "checked": 1, "unchecked": 1,
        "unchecked_paths": ["nowhere/missing.json"], "excluded": [], "reason": "forged",
    }
    with pytest.raises(report_module.ReportError, match="inputs_reverified"):
        _verify(tmp_path, repo, plan, payload)


def test_verification_rejects_a_report_that_omits_the_scope_claim(tmp_path):
    """No scope claim is not the same as a complete one."""
    repo, plan = _fixture(tmp_path)
    payload = passing_report(repo, plan)
    payload["plan"].pop("inputs_reverified")
    with pytest.raises(report_module.ReportError, match="inputs_reverified"):
        _verify(tmp_path, repo, plan, payload)


def test_verification_rejects_a_scope_whose_counts_do_not_add_up(tmp_path):
    repo, plan = _fixture(tmp_path)
    payload = passing_report(repo, plan)
    payload["plan"]["inputs_reverified"]["checked"] += 1
    with pytest.raises(report_module.ReportError, match="inputs_reverified"):
        _verify(tmp_path, repo, plan, payload)


def test_verification_rejects_excluding_an_external_repositorys_inputs(tmp_path):
    """A report cannot widen the excluded set to skip comparing an external input.

    The exclusion is derived from the trusted plan and the target repository, so
    naming another node's inputs as "the target's" is refused rather than
    accepted as a reason to look away. The counts here are self-consistent, so
    only the excluded *set* is wrong.
    """
    repo, _ = _fixture(tmp_path)
    external = _other_repo(tmp_path)
    plan = make_plan(tmp_path, repo,
                     inputs=[f"{REPO}/ci/environment.json", external], name="external-plan.json")
    payload = passing_report(repo, plan)
    payload["plan"]["inputs_reverified"] = {
        "verified": True, "total": 2, "checked": 1, "unchecked": 0,
        "unchecked_paths": [],
        "excluded": [{"path": external, "reason": "target_repository",
                      "bound_to": snapshot.resolve_commit(repo, "HEAD")}],
        "reason": "forged",
    }
    with pytest.raises(report_module.ReportError, match="excluded"):
        _verify(tmp_path, repo, plan, payload)


def test_verification_rejects_a_scope_that_does_not_match_the_workspace(tmp_path):
    """The claim has to be reproducible from the workspace being verified against."""
    repo, plan = _fixture(tmp_path)
    payload = passing_report(repo, plan)
    payload["plan"]["inputs_reverified"]["unchecked_paths"] = ["nowhere/missing.json"]
    with pytest.raises(report_module.ReportError, match="inputs_reverified"):
        _verify(tmp_path, repo, plan, payload)
