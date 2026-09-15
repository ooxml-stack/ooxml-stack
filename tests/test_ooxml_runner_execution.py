"""Shared runner execution: stage protocol, evidence, cache reuse, snapshots.

These tests never start Docker. They cover the path from "a stage ran" to "a
report is evidence", including every place the runner must refuse to announce a
pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

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
from ooxml_runner import cli, container, credentials, docker, execute, snapshot


def _reports(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    return reports


def _report(stages=("alpha",)):
    return {"status": "running", "commit": "a" * 40, "inputs": {},
            "stages": [{"name": name, "status": "not_run"} for name in stages]}


def _events(reports):
    return [json.loads(line) for line in (reports / "progress.jsonl").read_text().splitlines()]


# --- stage protocol -----------------------------------------------------------

def test_failing_stage_keeps_later_stages_unrun_and_writes_durable_events(tmp_path):
    reports = _reports(tmp_path)
    report = _report(("alpha", "beta"))

    def boom():
        raise RuntimeError("alpha exploded")

    with pytest.raises(RuntimeError, match="alpha exploded"):
        container.run_stages(reports, {"alpha": boom, "beta": lambda: None}, report, 5)
    assert [stage["status"] for stage in report["stages"]] == ["fail", "not_run"]
    events = _events(reports)
    assert [event["event"] for event in events] == ["gate_started", "stage_started", "stage_failed"]
    # The report named by the event already holds the failure when the event is written.
    assert json.loads(Path(events[-1]["report"]).read_text())["stages"][0]["status"] == "fail"
    assert "gate_passed" not in {event["event"] for event in events}


def test_input_drift_after_the_stages_never_announces_a_pass(tmp_path):
    reports = _reports(tmp_path)
    report = _report()
    report["inputs"] = {"f": "A"}
    container.run_stages(reports, {"alpha": lambda: None}, report, 5)
    with pytest.raises(container.StageError, match="changed tracked inputs"):
        container.finalize(tmp_path, reports, report, input_hashes=lambda root: {"f": "B"},
                           is_dirty=lambda root: False)
    assert report["status"] == "running"
    assert "gate_passed" not in {event["event"] for event in _events(reports)}


def test_a_clean_run_announces_pass_last(tmp_path):
    reports = _reports(tmp_path)
    report = _report()
    report["inputs"] = {"f": "A"}
    container.run_stages(reports, {"alpha": lambda: None}, report, 5)
    container.finalize(tmp_path, reports, report, input_hashes=lambda root: {"f": "A"},
                       is_dirty=lambda root: False)
    events = [event["event"] for event in _events(reports)]
    assert events[0] == "gate_started" and events[-1] == "gate_passed"
    assert report["status"] == "pass" and report["exit_code"] == 0


def test_a_dirty_snapshot_after_the_stages_never_announces_a_pass(tmp_path):
    reports = _reports(tmp_path)
    report = _report()
    container.run_stages(reports, {"alpha": lambda: None}, report, 5)
    with pytest.raises(container.StageError, match="dirty"):
        container.finalize(tmp_path, reports, report, input_hashes=lambda root: {},
                           is_dirty=lambda root: True)
    assert "gate_passed" not in {event["event"] for event in _events(reports)}


def test_stage_deadline_aborts_and_records_the_failure(tmp_path):
    reports = _reports(tmp_path)
    report = _report()

    def slow():
        time.sleep(30)

    with pytest.raises(TimeoutError):
        container.run_stages(reports, {"alpha": slow}, report, 1)
    assert report["stages"][0]["status"] == "fail"
    assert "TimeoutError" in report["stages"][0]["error"]


def test_failure_scrubs_secrets_from_the_report(tmp_path, monkeypatch):
    monkeypatch.setenv("OOXML_STACK_TOKEN", "runner-fixture-secret")
    reports = _reports(tmp_path)
    report = _report()

    def leak():
        raise RuntimeError("token runner-fixture-secret leaked")

    with pytest.raises(RuntimeError):
        container.run_stages(reports, {"alpha": leak}, report, 5)
    assert "runner-fixture-secret" not in json.dumps(report)
    assert "***" in report["stages"][0]["error"]


def test_secrets_never_reach_the_command_log(tmp_path, monkeypatch):
    monkeypatch.setenv("OOXML_STACK_TOKEN", "runner-fixture-secret")
    source = "import os; print(os.environ['OOXML_STACK_TOKEN'])"
    execute.run_command([sys.executable, "-c", source], "leak", tmp_path, tmp_path)
    assert (tmp_path / "leak.log").read_text() == "***\n"


def test_subprocess_failures_carry_the_exit_code_and_log_path(tmp_path):
    with pytest.raises(execute.CommandError) as caught:
        execute.run_command([sys.executable, "-c", "raise SystemExit(7)"], "boom", tmp_path, tmp_path)
    assert caught.value.exit_code == 7
    assert caught.value.log_path.endswith("boom.log")


def test_a_failing_command_keeps_its_log_and_never_reports_success(tmp_path):
    with pytest.raises(execute.CommandError, match="exit 3"):
        execute.run_command([sys.executable, "-c", "print('evidence'); raise SystemExit(3)"],
                            "stage", tmp_path, tmp_path)
    assert "evidence" in (tmp_path / "stage.log").read_text()


# --- cache reuse --------------------------------------------------------------

def _cached(tmp_path, repo, plan, mutate=None):
    commit = snapshot.resolve_commit(repo, "HEAD")
    directory = tmp_path / "out" / commit / "previous"
    directory.mkdir(parents=True)
    payload = passing_report(repo, plan)
    if mutate:
        mutate(payload)
    (directory / "report.json").write_text(json.dumps(payload))
    expected = expected_for(repo, plan)
    module = adapters.load(repo, "scripts.ci.adapter")
    return cli._cached_pass(directory.parent, expected, module, module.load_config(repo), {}), directory


def test_cache_reuse_requires_the_full_identity(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo)
    found, directory = _cached(tmp_path, repo, plan)
    assert found == directory


@pytest.mark.parametrize("fault", ["status", "runner", "plan", "inputs"])
def test_cache_reuse_is_refused_when_any_identity_differs(tmp_path, fault):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo)
    commit = snapshot.resolve_commit(repo, "HEAD")
    directory = tmp_path / "out" / commit / "previous"
    directory.mkdir(parents=True)
    payload = passing_report(repo, plan)
    if fault == "status":
        payload["status"] = "fail"
    (directory / "report.json").write_text(json.dumps(payload))
    expected = expected_for(repo, plan)
    if fault == "runner":
        expected["runner_commit"] = "0" * 40
    elif fault == "plan":
        expected["plan_sha256"] = "0" * 64
    elif fault == "inputs":
        expected["inputs_digest"] = "0" * 64
    module = adapters.load(repo, "scripts.ci.adapter")
    assert cli._cached_pass(directory.parent, expected, module, module.load_config(repo), {}) is None


def test_a_broken_report_does_not_hide_a_valid_one(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo)
    commit = snapshot.resolve_commit(repo, "HEAD")
    broken = tmp_path / "out" / commit / "000-broken"
    broken.mkdir(parents=True)
    (broken / "report.json").write_text("{interrupted")
    valid = tmp_path / "out" / commit / "valid"
    valid.mkdir(parents=True)
    (valid / "report.json").write_text(json.dumps(passing_report(repo, plan)))
    module = adapters.load(repo, "scripts.ci.adapter")
    found = cli._cached_pass(broken.parent, expected_for(repo, plan), module,
                             module.load_config(repo), {})
    assert found == valid


def test_a_report_for_another_commit_is_not_reused(tmp_path):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo)
    found, _ = _cached(tmp_path, repo, plan, mutate=lambda payload: payload.__setitem__("commit", "0" * 40))
    assert found is None


# --- the recursion guard ------------------------------------------------------

def test_the_plan_shell_text_is_never_executed(tmp_path, monkeypatch):
    """A workflow step that calls the entry point is evidence, not a command."""
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo)
    payload = json.loads(plan.read_text())
    payload["full"][REPO]["jobs"][0]["steps"] = [
        {"name": "Run the shared gate", "run": "touch " + str(tmp_path / "recursion-marker")}
    ]
    plan.write_text(json.dumps(payload))
    monkeypatch.setattr(docker, "execute", pytest.fail)
    monkeypatch.setattr(snapshot, "credential", pytest.fail)
    cli.describe_repository(root=tmp_path, repo=REPO, commit="HEAD",
                            runner_commit=RUNNER_COMMIT, plan=plan)
    assert not (tmp_path / "recursion-marker").exists()


def test_the_container_command_never_uses_a_shell(tmp_path):
    argv = docker.command(
        workspace=tmp_path, reports=tmp_path / "reports", runner_root=tmp_path, plan=tmp_path / "plan.json",
        config={"image": "fixture@sha256:" + "0" * 64, "platform": "linux/amd64"},
        commit="a" * 40, name="fixture", cpus=2, repository=REPO, adapter="scripts.ci.adapter",
    )
    assert argv[:2] == ["docker", "run"]
    assert "sh" not in argv and "-c" not in argv
    assert argv[-4:] == ["--repository", REPO, "--adapter", "scripts.ci.adapter"]
    assert argv[-7:-4] == ["python", "-m", "ooxml_runner.bootstrap"]


def test_the_container_names_the_runner_mount_for_the_adapter_bridge(tmp_path):
    """The adapter finds the runner through its own repository's bridge."""
    argv = docker.command(
        workspace=tmp_path, reports=tmp_path / "reports", runner_root=tmp_path, plan=tmp_path / "plan.json",
        config={"image": "fixture@sha256:" + "0" * 64, "platform": "linux/amd64"},
        commit="a" * 40, name="fixture", cpus=2, repository=REPO, adapter="scripts.ci.adapter",
    )
    assert "OOXML_RUNNER_ROOT=/runner" in argv
    assert "PYTHONPATH=/runner" in argv


def test_the_container_trusts_its_bind_mounts_as_git_safe_directories(tmp_path):
    """A Linux host owns the runner mount as another uid; Git refuses it otherwise."""
    argv = docker.command(
        workspace=tmp_path, reports=tmp_path / "reports", runner_root=tmp_path, plan=tmp_path / "plan.json",
        config={"image": "fixture@sha256:" + "0" * 64, "platform": "linux/amd64"},
        commit="a" * 40, name="fixture", cpus=2, repository=REPO, adapter="scripts.ci.adapter",
    )
    assert "GIT_CONFIG_COUNT=1" in argv
    assert "GIT_CONFIG_KEY_0=safe.directory" in argv
    assert "GIT_CONFIG_VALUE_0=/runner" in argv


def test_configuring_credentials_keeps_the_git_config_the_container_injected(monkeypatch):
    """The auth header must not evict the safe.directory entry it shares a protocol with."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "safe.directory")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/runner")
    monkeypatch.delenv(credentials.TOKEN_VAR, raising=False)

    credentials.configure("token-value")

    assert os.environ["GIT_CONFIG_COUNT"] == "2"
    assert os.environ["GIT_CONFIG_KEY_0"] == "safe.directory"
    assert os.environ["GIT_CONFIG_VALUE_0"] == "/runner"
    assert os.environ["GIT_CONFIG_KEY_1"] == "http.https://github.com/.extraheader"
    assert os.environ["GIT_CONFIG_VALUE_1"].startswith("AUTHORIZATION: basic ")
    assert os.environ[credentials.TOKEN_VAR] == "token-value"


def test_configuring_credentials_twice_does_not_duplicate_the_auth_header(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "safe.directory")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/runner")

    credentials.configure("token-value")
    credentials.configure("token-value")

    assert os.environ["GIT_CONFIG_COUNT"] == "2"
    assert os.environ["GIT_CONFIG_KEY_1"] == "http.https://github.com/.extraheader"


def test_configuring_credentials_tolerates_a_broken_injected_count(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "not-a-number")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "safe.directory")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/runner")

    credentials.configure("token-value")

    assert os.environ["GIT_CONFIG_COUNT"] == "1"
    assert os.environ["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"


def test_repository_keys_with_spaces_survive_as_single_arguments(tmp_path):
    argv = docker.command(
        workspace=tmp_path / "a b", reports=tmp_path / "reports", runner_root=tmp_path,
        plan=tmp_path / "plan.json",
        config={"image": "fixture@sha256:" + "0" * 64, "platform": "linux/amd64"},
        commit="a" * 40, name="fixture", cpus=2, repository="ooxml operation engine",
        adapter="scripts.ci.adapter",
    )
    assert any(arg.endswith(f"source={tmp_path}/a b,target=/input,readonly") for arg in argv)
    assert "ooxml operation engine" in argv


# --- snapshots ----------------------------------------------------------------

def test_git_plumbing_refuses_a_revision_that_is_not_a_commit(tmp_path):
    repo = make_repo(tmp_path)
    with pytest.raises(snapshot.SnapshotError):
        snapshot.resolve_commit(repo, "HEAD^{tree}")


def test_snapshot_checkout_is_the_requested_commit(tmp_path):
    repo = make_repo(tmp_path)
    commit = snapshot.resolve_commit(repo, "HEAD")
    (repo / "ci/environment.json").write_text("{}")
    destination = snapshot.checkout(repo, commit, tmp_path / "snapshot")
    assert snapshot.git(destination, "rev-parse", "HEAD") == commit
    assert json.loads((destination / "ci/environment.json").read_text()) == {"schema_version": 1}


def test_a_dirty_worktree_never_becomes_the_verification_subject(tmp_path):
    repo = make_repo(tmp_path)
    commit = snapshot.resolve_commit(repo, "HEAD")
    (repo / "ci/environment.json").write_text('{"dirty": true}')
    assert snapshot.is_exact(repo, commit) is False
    with snapshot.materialize(repo, commit) as subject:
        assert subject != repo
        assert json.loads((subject / "ci/environment.json").read_text()) == {"schema_version": 1}


def test_the_runner_is_importable_without_the_engine_repository():
    """The runner must not depend on any repository it verifies."""
    probe = "import ooxml_runner, ooxml_runner.cli, ooxml_runner.entry, ooxml_runner.bootstrap; print('ok')"
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                            cwd=str(Path(__file__).resolve().parents[1]), check=True)
    assert result.stdout.strip() == "ok"