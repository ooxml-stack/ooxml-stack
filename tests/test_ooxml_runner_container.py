"""Container launch, credential handover, command execution and snapshots.

Nothing here starts Docker: the transport is exercised with local subprocesses,
so what is under test is the runner's own argv construction, its stdin handover
and its snapshot semantics.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from runner_fixtures import REPO, make_repo

from ooxml_runner import credentials, docker, execute, snapshot


def test_the_container_command_never_uses_a_shell(tmp_path):
    argv = docker.command(
        workspace=tmp_path, reports=tmp_path / "reports", runner_root=tmp_path, plan=tmp_path / "plan.json",
        config={"image": "fixture@sha256:" + "0" * 64, "platform": "linux/amd64"},
        commit="a" * 40, runner_commit="b" * 40, name="fixture", cpus=2, repository=REPO, adapter="scripts.ci.adapter",
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
        commit="a" * 40, runner_commit="b" * 40, name="fixture", cpus=2, repository=REPO, adapter="scripts.ci.adapter",
    )
    assert "OOXML_RUNNER_ROOT=/runner" in argv
    assert "PYTHONPATH=/runner" in argv


def test_the_container_is_told_which_runner_commit_to_execute(tmp_path):
    """The container proves the mounted runner is the pinned one."""
    argv = docker.command(
        workspace=tmp_path, reports=tmp_path / "reports", runner_root=tmp_path, plan=tmp_path / "plan.json",
        config={"image": "fixture@sha256:" + "0" * 64, "platform": "linux/amd64"},
        commit="a" * 40, runner_commit="b" * 40, name="fixture", cpus=2, repository=REPO, adapter="scripts.ci.adapter",
    )
    assert "OOXML_CI_RUNNER_COMMIT=" + "b" * 40 in argv


def test_the_container_trusts_its_bind_mounts_as_git_safe_directories(tmp_path):
    """A Linux host owns the runner mount as another uid; Git refuses it otherwise."""
    argv = docker.command(
        workspace=tmp_path, reports=tmp_path / "reports", runner_root=tmp_path, plan=tmp_path / "plan.json",
        config={"image": "fixture@sha256:" + "0" * 64, "platform": "linux/amd64"},
        commit="a" * 40, runner_commit="b" * 40, name="fixture", cpus=2, repository=REPO, adapter="scripts.ci.adapter",
    )
    assert "GIT_CONFIG_COUNT=1" in argv
    assert "GIT_CONFIG_KEY_0=safe.directory" in argv
    assert "GIT_CONFIG_VALUE_0=/runner" in argv


def test_repository_keys_with_spaces_survive_as_single_arguments(tmp_path):
    argv = docker.command(
        workspace=tmp_path / "a b", reports=tmp_path / "reports", runner_root=tmp_path,
        plan=tmp_path / "plan.json",
        config={"image": "fixture@sha256:" + "0" * 64, "platform": "linux/amd64"},
        commit="a" * 40, runner_commit="b" * 40, name="fixture", cpus=2, repository="ooxml operation engine",
        adapter="scripts.ci.adapter",
    )
    assert any(arg.endswith(f"source={tmp_path}/a b,target=/input,readonly") for arg in argv)
    assert "ooxml operation engine" in argv


# --- credentials --------------------------------------------------------------

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


# --- command execution --------------------------------------------------------

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


def test_a_container_that_dies_before_reading_stdin_reports_its_own_exit_status(tmp_path):
    """A child that never drains stdin closes the pipe; that must not mask its status."""
    source = "import os, time; os.close(0); time.sleep(0.2); raise SystemExit(97)"
    argv = [sys.executable, "-c", source]
    assert docker.execute(argv, tmp_path, "fixture-token", 30, "fixture-container") == 97


def test_a_broken_stdin_pipe_is_not_reported_as_the_container_result():
    """The guard itself: a closed pipe on the token write is swallowed, not raised."""

    class Closed:
        def write(self, _data):
            raise BrokenPipeError(32, "Broken pipe")

        def close(self):
            raise BrokenPipeError(32, "Broken pipe")

    docker._hand_over_token(SimpleNamespace(stdin=Closed()), "fixture-token")


def test_a_container_that_never_reads_stdin_still_leaves_a_log(tmp_path):
    argv = [sys.executable, "-c", "print('early exit'); raise SystemExit(3)"]
    assert docker.execute(argv, tmp_path, "fixture-token", 30, "fixture-container") == 3
    assert "early exit" in (tmp_path / "run.log").read_text()


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