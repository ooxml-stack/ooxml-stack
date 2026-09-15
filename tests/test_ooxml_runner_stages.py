"""The stage protocol: ordering, deadlines, durable events, terminal ordering.

The last point is the one that regressed: ``gate_passed`` and ``gate_failed``
used to be written while the report on disk still said ``running``, so a
progress consumer that read the report named by the event saw a contradictory
state. Every terminal assertion here reads the report from disk *inside* the
event callback, not after the call returns.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from runner_fixtures import RUNNER_COMMIT

from ooxml_runner import container, entry
from ooxml_runner import report as report_module

FIXTURE_ADAPTER = '''
"""Fixture adapter for the container entry."""

STAGES = ["alpha"]


def describe(root):
    return {"stages": list(STAGES), "environment": {}, "implementation": "fixture",
            "static_commands": [], "runtime_steps": []}


def load_config(root):
    return {"image": "fixture@sha256:" + "0" * 64, "stage_timeout_seconds": 5}


def input_hashes(root):
    return {}


def is_dirty(root):
    return False


def operations(root, reports, config):
    return {name: (lambda name=name: {"stage": name}) for name in STAGES}


def verify_report(report, commit, config, inputs):
    pass
'''

FAILING_ADAPTER = FIXTURE_ADAPTER.replace(
    'return {name: (lambda name=name: {"stage": name}) for name in STAGES}',
    'raise ValueError("fixture failure")',
)


def _reports(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    return reports


def _report(stages=("alpha",)):
    return {"status": "running", "commit": "a" * 40, "inputs": {},
            "stages": [{"name": name, "status": "not_run"} for name in stages]}


def _events(reports):
    return [json.loads(line) for line in (reports / "progress.jsonl").read_text().splitlines()]


def _observe_terminal(monkeypatch, seen):
    """Record the on-disk report at the moment each terminal event is written."""
    real = container.progress_event

    def observe(reports, event, **fields):
        if event in ("gate_passed", "gate_failed"):
            seen.append((event, report_module.load(Path(reports))))
        real(reports, event, **fields)

    monkeypatch.setattr(container, "progress_event", observe)


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
    assert json.loads(Path(events[-1]["report"]).read_text())["stages"][0]["status"] == "fail"
    assert "gate_passed" not in {event["event"] for event in events}


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


# --- terminal report before terminal event ------------------------------------

def test_gate_passed_is_written_only_after_the_pass_is_on_disk(tmp_path, monkeypatch):
    reports = _reports(tmp_path)
    report = _report()
    seen = []
    _observe_terminal(monkeypatch, seen)

    container.run_stages(reports, {"alpha": lambda: None}, report, 5)
    container.finalize(tmp_path, reports, report, input_hashes=lambda root: {},
                       is_dirty=lambda root: False)

    assert len(seen) == 1
    event, on_disk = seen[0]
    assert event == "gate_passed"
    assert on_disk["status"] == "pass"
    assert on_disk["exit_code"] == 0
    assert on_disk["finished_at"]


def test_gate_failed_is_written_only_after_the_failure_is_on_disk(tmp_path, monkeypatch):
    reports = _reports(tmp_path)
    report = _report()
    seen = []
    _observe_terminal(monkeypatch, seen)

    container.run_stages(reports, {"alpha": lambda: None}, report, 5)
    container.fail(reports, report, ValueError("fixture failure"))

    assert len(seen) == 1
    event, on_disk = seen[0]
    assert event == "gate_failed"
    assert on_disk["status"] == "fail"
    assert on_disk["finished_at"]
    assert "fixture failure" in on_disk["error"]


def test_a_failed_terminal_save_never_announces_a_pass(tmp_path, monkeypatch):
    reports = _reports(tmp_path)
    report = _report()
    written = []
    monkeypatch.setattr(container, "progress_event",
                        lambda reports, event, **fields: written.append(event))

    def refuse(reports, report):
        raise OSError("disk is full")

    monkeypatch.setattr(container, "save_report", refuse)
    with pytest.raises(OSError):
        container.finalize(tmp_path, reports, report, input_hashes=lambda root: {},
                           is_dirty=lambda root: False)
    assert "gate_passed" not in written


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


def test_a_dirty_snapshot_after_the_stages_never_announces_a_pass(tmp_path):
    reports = _reports(tmp_path)
    report = _report()
    container.run_stages(reports, {"alpha": lambda: None}, report, 5)
    with pytest.raises(container.StageError, match="dirty"):
        container.finalize(tmp_path, reports, report, input_hashes=lambda root: {},
                           is_dirty=lambda root: True)
    assert "gate_passed" not in {event["event"] for event in _events(reports)}


# --- the container entry ------------------------------------------------------

def _run_entry(tmp_path, monkeypatch, adapter, seen, name="fixture_adapter"):
    subject = tmp_path / "subject"
    subject.mkdir(exist_ok=True)
    (subject / f"{name}.py").write_text(adapter)
    reports = tmp_path / "reports"
    report_module.save(reports, report_module.new_report(
        repository="fixture", commit="a" * 40,
        runner={"commit": RUNNER_COMMIT, "source_sha256": "b" * 64},
        plan={}, binding={}, image="fixture", inputs={},
    ))
    monkeypatch.setenv("OOXML_CI_RUNNER_COMMIT", RUNNER_COMMIT)
    _observe_terminal(monkeypatch, seen)
    return entry.main(["--repository", "fixture", "--adapter", name,
                       "--root", str(subject), "--reports", str(reports)]), reports


def test_entry_main_writes_the_terminal_report_before_the_pass_event(tmp_path, monkeypatch):
    seen = []
    code, reports = _run_entry(tmp_path, monkeypatch, FIXTURE_ADAPTER, seen)

    assert code == 0
    assert [(event, disk["status"], disk["exit_code"]) for event, disk in seen] == \
        [("gate_passed", "pass", 0)]
    assert report_module.load(reports)["finished_at"]


def test_entry_main_writes_the_terminal_report_before_the_failure_event(tmp_path, monkeypatch):
    seen = []
    code, reports = _run_entry(tmp_path, monkeypatch, FAILING_ADAPTER, seen)

    assert code == 1
    assert [(event, disk["status"]) for event, disk in seen] == [("gate_failed", "fail")]
    assert "fixture failure" in report_module.load(reports)["error"]


def test_entry_main_refuses_a_runner_that_is_not_the_pinned_commit(tmp_path, monkeypatch):
    """The container proves which runner it actually executed."""
    seen = []
    monkeypatch.setenv("OOXML_CI_RUNNER_COMMIT", "0" * 40)
    subject = tmp_path / "subject"
    subject.mkdir()
    (subject / "fixture_adapter.py").write_text(FIXTURE_ADAPTER)
    reports = tmp_path / "reports"
    report_module.save(reports, report_module.new_report(
        repository="fixture", commit="a" * 40, runner={}, plan={}, binding={},
        image="fixture", inputs={},
    ))
    _observe_terminal(monkeypatch, seen)

    code = entry.main(["--repository", "fixture", "--adapter", "fixture_adapter",
                       "--root", str(subject), "--reports", str(reports)])
    assert code == 1
    assert [event for event, _ in seen] == ["gate_failed"]