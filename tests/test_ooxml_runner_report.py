"""Report verification: runner source identity and plan binding are checked.

A report is evidence only when the caller can re-derive every identity in it.
The runner commit was already checked; the runner *source* hash and the plan
binding were not, so a report whose source hash had been zeroed or deleted, or
whose binding named a workflow, job and adapter that do not exist, still passed.

The same rules serve ordinary verification and cache reuse, and verification
never rewrites the report it is judging.
"""

from __future__ import annotations

import json

import pytest
from runner_fixtures import (
    REPO,
    RUNNER_COMMIT,
    expected_for,
    make_plan,
    make_repo,
    passing_report,
)

from ooxml_runner import adapter as adapters
from ooxml_runner import cli, snapshot
from ooxml_runner import report as report_module


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


def test_verification_accepts_a_report_with_the_right_identity_and_binding(tmp_path):
    repo, plan = _fixture(tmp_path)
    assert _verify(tmp_path, repo, plan, passing_report(repo, plan))["result"] == "pass"


def test_verification_rejects_a_wrong_runner_source_hash(tmp_path):
    repo, plan = _fixture(tmp_path)
    payload = passing_report(repo, plan)
    payload["runner"]["source_sha256"] = "0" * 64
    with pytest.raises(report_module.ReportError, match="source"):
        _verify(tmp_path, repo, plan, payload)


def test_verification_rejects_a_missing_runner_source_hash(tmp_path):
    repo, plan = _fixture(tmp_path)
    payload = passing_report(repo, plan)
    payload["runner"].pop("source_sha256")
    with pytest.raises(report_module.ReportError, match="source"):
        _verify(tmp_path, repo, plan, payload)


@pytest.mark.parametrize("value", [0, None, [], {"sha256": "0" * 64}])
def test_verification_rejects_a_wrongly_typed_runner_source_hash(tmp_path, value):
    repo, plan = _fixture(tmp_path)
    payload = passing_report(repo, plan)
    payload["runner"]["source_sha256"] = value
    with pytest.raises(report_module.ReportError, match="source"):
        _verify(tmp_path, repo, plan, payload)


def test_verification_rejects_a_missing_runner_block(tmp_path):
    repo, plan = _fixture(tmp_path)
    payload = passing_report(repo, plan)
    payload.pop("runner")
    with pytest.raises(report_module.ReportError, match="runner"):
        _verify(tmp_path, repo, plan, payload)


@pytest.mark.parametrize("field", ["workflow", "jobs", "adapter"])
def test_verification_rejects_a_binding_that_differs_from_the_plan(tmp_path, field):
    repo, plan = _fixture(tmp_path)
    payload = passing_report(repo, plan)
    payload["binding"][field] = "wrong.yml" if field != "jobs" else ["wrong"]
    with pytest.raises(report_module.ReportError, match="binding"):
        _verify(tmp_path, repo, plan, payload)


def test_verification_rejects_a_missing_binding(tmp_path):
    repo, plan = _fixture(tmp_path)
    payload = passing_report(repo, plan)
    payload.pop("binding")
    with pytest.raises(report_module.ReportError, match="binding"):
        _verify(tmp_path, repo, plan, payload)


@pytest.mark.parametrize("value", [["wrong-type"], "wrong-type", 7, None])
def test_verification_rejects_a_malformed_plan_block(tmp_path, value):
    """A structurally wrong field is a report error, not a crash.

    ``runner`` and ``binding`` were already type-checked; ``plan`` was not, so a
    valid JSON report whose ``plan`` was a non-empty list raised AttributeError
    out of the verifier instead of being classified.
    """
    repo, plan = _fixture(tmp_path)
    payload = passing_report(repo, plan)
    payload["plan"] = value
    with pytest.raises(report_module.ReportError, match="plan"):
        _verify(tmp_path, repo, plan, payload)


def test_verification_never_rewrites_the_report_under_test(tmp_path):
    """A historical report keeps its own execution identity."""
    repo, plan = _fixture(tmp_path)
    payload = passing_report(repo, plan)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(payload, indent=2))
    before = path.read_text()

    cli.verify_report_file(root=tmp_path, repo=REPO, commit=snapshot.resolve_commit(repo, "HEAD"),
                           runner_commit=RUNNER_COMMIT, plan=plan, report=path)
    assert path.read_text() == before


# --- cache reuse --------------------------------------------------------------

def _cache(tmp_path, repo, plan, mutate=None):
    commit = snapshot.resolve_commit(repo, "HEAD")
    directory = tmp_path / "out" / commit / "previous"
    directory.mkdir(parents=True)
    payload = passing_report(repo, plan)
    if mutate:
        mutate(payload)
    (directory / "report.json").write_text(json.dumps(payload))
    module = adapters.load(repo, "scripts.ci.adapter")
    found = cli._cached_pass(directory.parent, expected_for(repo, plan), module,
                             module.load_config(repo), {})
    return found, directory


def test_a_cache_entry_with_the_right_identity_is_reused(tmp_path):
    repo, plan = _fixture(tmp_path)
    found, directory = _cache(tmp_path, repo, plan)
    assert found == directory


@pytest.mark.parametrize("mutate", [
    lambda payload: payload["runner"].update(source_sha256="0" * 64),
    lambda payload: payload["runner"].pop("source_sha256"),
    lambda payload: payload.update(binding={"workflow": "missing.yml", "jobs": ["wrong"],
                                            "adapter": "scripts.ci.other"}),
    lambda payload: payload.pop("binding"),
])
def test_a_cache_entry_with_the_wrong_identity_is_not_reused(tmp_path, mutate):
    repo, plan = _fixture(tmp_path)
    found, _ = _cache(tmp_path, repo, plan, mutate=mutate)
    assert found is None


def test_a_broken_cache_entry_does_not_hide_a_valid_one(tmp_path):
    repo, plan = _fixture(tmp_path)
    commit = snapshot.resolve_commit(repo, "HEAD")
    broken = tmp_path / "out" / commit / "000-broken"
    broken.mkdir(parents=True)
    (broken / "report.json").write_text(json.dumps(
        passing_report(repo, plan, binding={"workflow": "missing.yml", "jobs": ["wrong"],
                                                  "adapter": "scripts.ci.other"})))
    valid = tmp_path / "out" / commit / "valid"
    valid.mkdir(parents=True)
    (valid / "report.json").write_text(json.dumps(passing_report(repo, plan)))
    module = adapters.load(repo, "scripts.ci.adapter")

    found = cli._cached_pass(broken.parent, expected_for(repo, plan), module,
                             module.load_config(repo), {})
    assert found == valid


def _cache_dir(tmp_path, repo, plan, name, mutate):
    commit = snapshot.resolve_commit(repo, "HEAD")
    directory = tmp_path / "out" / commit / name
    directory.mkdir(parents=True)
    payload = passing_report(repo, plan)
    mutate(payload)
    (directory / "report.json").write_text(json.dumps(payload))
    return directory


def test_a_structurally_broken_cache_entry_does_not_hide_a_valid_one(tmp_path):
    """The reviewed case: a valid JSON report whose ``plan`` is a list."""
    repo, plan = _fixture(tmp_path)
    broken = _cache_dir(tmp_path, repo, plan, "000-broken", lambda p: p.update(plan=["wrong-type"]))
    valid = _cache_dir(tmp_path, repo, plan, "100-valid", lambda p: None)
    module = adapters.load(repo, "scripts.ci.adapter")

    found = cli._cached_pass(broken.parent, expected_for(repo, plan), module,
                             module.load_config(repo), {})
    assert found == valid


def test_a_structurally_broken_cache_entry_alone_means_no_reuse(tmp_path):
    """No valid entry: the caller must fall through to a fresh run, not crash."""
    repo, plan = _fixture(tmp_path)
    broken = _cache_dir(tmp_path, repo, plan, "000-broken", lambda p: p.update(plan=["wrong-type"]))
    module = adapters.load(repo, "scripts.ci.adapter")

    found = cli._cached_pass(broken.parent, expected_for(repo, plan), module,
                             module.load_config(repo), {})
    assert found is None


def test_an_unexpected_cache_failure_is_not_swallowed(tmp_path, monkeypatch):
    """Only classified report problems are skipped; a real bug must surface."""
    repo, plan = _fixture(tmp_path)
    broken = _cache_dir(tmp_path, repo, plan, "000-broken", lambda p: None)
    module = adapters.load(repo, "scripts.ci.adapter")

    def explode(candidate, expected):
        raise AttributeError("programming error, not a bad report")

    monkeypatch.setattr(report_module, "verify_generic", explode)
    with pytest.raises(AttributeError, match="programming error"):
        cli._cached_pass(broken.parent, expected_for(repo, plan), module,
                         module.load_config(repo), {})


# --- the real CLI -------------------------------------------------------------

def _cli(tmp_path, repo, plan, payload):
    path = tmp_path / "cli-report.json"
    path.write_text(json.dumps(payload))
    return cli.main([
        "verify-report", "--root", str(tmp_path), "--repo", REPO,
        "--commit", snapshot.resolve_commit(repo, "HEAD"), "--runner-commit", RUNNER_COMMIT,
        "--plan", str(plan), "--report", str(path),
    ])


def test_the_verify_cli_accepts_a_valid_report_and_refuses_the_variants(tmp_path):
    repo, plan = _fixture(tmp_path)
    assert _cli(tmp_path, repo, plan, passing_report(repo, plan)) == 0

    wrong_source = passing_report(repo, plan)
    wrong_source["runner"]["source_sha256"] = "0" * 64
    assert _cli(tmp_path, repo, plan, wrong_source) == 1

    wrong_binding = passing_report(repo, plan)
    wrong_binding["binding"]["adapter"] = "scripts.ci.other"
    assert _cli(tmp_path, repo, plan, wrong_binding) == 1

    missing_binding = passing_report(repo, plan)
    missing_binding.pop("binding")
    assert _cli(tmp_path, repo, plan, missing_binding) == 1