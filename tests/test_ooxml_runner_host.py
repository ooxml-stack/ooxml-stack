"""Host-side finalization when the container never finishes its own report.

``run_repository`` writes a ``running`` skeleton and then launches the
container. When the container dies before its first stage - or exits zero with a
report the host refuses - the host used to raise and leave that skeleton on
disk forever, with no ``progress.jsonl`` at all. A consumer reading the report
directory could not tell the run had ended, and could not tell how.

The host now completes the terminal state it already observed. A failure the
container did record keeps its own error, stages and logs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from runner_fixtures import REPO, RUNNER_COMMIT, make_plan, make_repo, passing_report

from ooxml_runner import adapter as adapters
from ooxml_runner import cli, docker, snapshot
from ooxml_runner import report as report_module


def _fixture(tmp_path):
    repo = make_repo(tmp_path)
    return repo, make_plan(tmp_path, repo), tmp_path / "out"


def _stub_transport(monkeypatch, behave):
    """Replace only the Docker transport: the real ``docker.execute`` still runs."""
    real = docker.execute
    monkeypatch.setattr(docker, "cpu_limit", lambda: 1)
    monkeypatch.setattr(snapshot, "credential", lambda: "fixture-token")

    def execute(argv, reports, token, timeout, name):
        return behave(real, reports, token, timeout, name)

    monkeypatch.setattr(docker, "execute", execute)


def _python_child(source, code=0):
    return [sys.executable, "-c", f"{source}; raise SystemExit({code})"]


def _only_report(output):
    path = next(Path(output).glob("*/*/report.json"))
    return report_module.load(path), path.parent


def _events(reports):
    path = Path(reports) / "progress.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _run(tmp_path, repo, plan, output, **kwargs):
    return cli.run_repository(root=tmp_path, repo=REPO, commit="HEAD",
                              runner_commit=RUNNER_COMMIT, plan=plan, output=output, **kwargs)


def test_an_early_container_exit_leaves_a_finished_failure_report(tmp_path, monkeypatch):
    """The reviewed case: a child that closes stdin and exits 97."""
    repo, plan, output = _fixture(tmp_path)
    source = "import os, time; os.close(0); time.sleep(0.2); print('early-exit-control')"
    _stub_transport(monkeypatch, lambda real, reports, token, timeout, name:
                    real(_python_child(source, 97), reports, token, timeout, name))

    with pytest.raises(RuntimeError, match="97"):
        _run(tmp_path, repo, plan, output)

    payload, reports = _only_report(output)
    assert payload["status"] == "fail"
    assert payload["exit_code"] == 97
    assert payload["finished_at"]
    assert "97" in payload["error"]
    assert [stage["status"] for stage in payload["stages"]] == ["not_run", "not_run"]
    assert [event["event"] for event in _events(reports)][-1] == "gate_failed"
    assert "early-exit-control" in (reports / "run.log").read_text()


def test_a_launch_failure_leaves_a_finished_failure_report(tmp_path, monkeypatch):
    repo, plan, output = _fixture(tmp_path)

    def refuse(*args, **kwargs):
        raise OSError("docker is not installed")

    monkeypatch.setattr(docker, "cpu_limit", lambda: 1)
    monkeypatch.setattr(snapshot, "credential", lambda: "fixture-token")
    monkeypatch.setattr(docker, "execute", refuse)

    with pytest.raises(OSError, match="docker is not installed"):
        _run(tmp_path, repo, plan, output)

    payload, _ = _only_report(output)
    assert payload["status"] == "fail"
    assert payload["exit_code"] == 1
    assert payload["finished_at"]
    assert "docker is not installed" in payload["error"]


def test_a_container_timeout_leaves_a_finished_failure_report(tmp_path, monkeypatch):
    repo, plan, output = _fixture(tmp_path)
    _stub_transport(monkeypatch, lambda real, reports, token, timeout, name:
                    real(_python_child("import time; time.sleep(30)", 0), reports, token, 1, name))

    with pytest.raises(subprocess.TimeoutExpired):
        _run(tmp_path, repo, plan, output, timeout=1)

    payload, _ = _only_report(output)
    assert payload["status"] == "fail"
    assert payload["finished_at"]
    assert "TimeoutExpired" in payload["error"]


def test_a_cancelled_run_leaves_a_finished_failure_report(tmp_path, monkeypatch):
    repo, plan, output = _fixture(tmp_path)
    monkeypatch.setattr(docker, "cpu_limit", lambda: 1)
    monkeypatch.setattr(snapshot, "credential", lambda: "fixture-token")

    def cancel(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(docker, "execute", cancel)

    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, repo, plan, output)

    payload, _ = _only_report(output)
    assert payload["status"] == "fail"
    assert payload["finished_at"]
    assert "KeyboardInterrupt" in payload["error"]


def test_a_stage_failure_the_container_recorded_is_preserved(tmp_path, monkeypatch):
    """The host must not replace a specific failure with a vaguer one."""
    repo, plan, output = _fixture(tmp_path)

    def fail_inside(reports):
        payload = report_module.load(reports)
        payload["stages"][0].update(status="fail", error="ValueError: stage exploded")
        payload.update(status="fail", exit_code=1, error="ValueError: stage exploded",
                       finished_at=report_module.utc_now())
        report_module.save(reports, payload)
        report_module.progress_event(reports, "gate_failed", error=payload["error"],
                                     report=str(Path(reports) / "report.json"))
        return 1

    _stub_transport(monkeypatch, lambda real, reports, token, timeout, name: fail_inside(reports))

    with pytest.raises(RuntimeError, match="exit 1"):
        _run(tmp_path, repo, plan, output)

    payload, reports = _only_report(output)
    assert payload["status"] == "fail"
    assert payload["error"] == "ValueError: stage exploded"
    assert payload["stages"][0]["status"] == "fail"
    assert [event["event"] for event in _events(reports)].count("gate_failed") == 1


def test_a_zero_exit_with_an_unfinished_report_is_recorded_as_a_failure(tmp_path, monkeypatch):
    repo, plan, output = _fixture(tmp_path)
    _stub_transport(monkeypatch, lambda real, reports, token, timeout, name: 0)

    with pytest.raises(report_module.ReportError):
        _run(tmp_path, repo, plan, output)

    payload, reports = _only_report(output)
    assert payload["status"] == "fail"
    assert payload["finished_at"]
    assert [event["event"] for event in _events(reports)][-1] == "gate_failed"


def test_a_zero_exit_with_a_refused_report_is_recorded_as_a_failure(tmp_path, monkeypatch):
    """The container says pass; the host's contract refuses it."""
    repo, plan, output = _fixture(tmp_path)

    def pass_but_wrong(reports):
        payload = passing_report(repo, plan)
        payload["image"] = "other@sha256:" + "0" * 64
        report_module.save(reports, payload)
        return 0

    _stub_transport(monkeypatch, lambda real, reports, token, timeout, name: pass_but_wrong(reports))

    with pytest.raises(adapters.AdapterError, match="image mismatch"):
        _run(tmp_path, repo, plan, output)

    payload, reports = _only_report(output)
    assert payload["status"] == "fail"
    assert payload["finished_at"]
    assert [event["event"] for event in _events(reports)][-1] == "gate_failed"


def test_a_normal_run_still_reports_success(tmp_path, monkeypatch):
    repo, plan, output = _fixture(tmp_path)

    def pass_through(reports):
        report_module.save(reports, passing_report(repo, plan))
        return 0

    _stub_transport(monkeypatch, lambda real, reports, token, timeout, name: pass_through(reports))

    result = _run(tmp_path, repo, plan, output)
    assert result["result"] == "pass"
    payload, _ = _only_report(output)
    assert payload["status"] == "pass" and payload["exit_code"] == 0


def test_a_failed_run_is_never_reused_from_the_cache(tmp_path, monkeypatch):
    repo, plan, output = _fixture(tmp_path)
    _stub_transport(monkeypatch, lambda real, reports, token, timeout, name:
                    real(_python_child("pass", 97), reports, token, timeout, name))

    with pytest.raises(RuntimeError, match="97"):
        _run(tmp_path, repo, plan, output)

    launched = []

    def again(*args, **kwargs):
        launched.append(args)
        raise RuntimeError("launched again")

    monkeypatch.setattr(docker, "execute", again)
    with pytest.raises(RuntimeError, match="launched again"):
        _run(tmp_path, repo, plan, output, reuse_success=True)
    assert launched, "a failed report must not be reused as a pass"


def test_a_failure_before_the_report_exists_fabricates_nothing(tmp_path):
    _repo, plan, output = _fixture(tmp_path)
    with pytest.raises(Exception, match="runner commit mismatch"):
        cli.run_repository(root=tmp_path, repo=REPO, commit="HEAD",
                           runner_commit="0" * 40, plan=plan, output=output)
    assert not output.exists()