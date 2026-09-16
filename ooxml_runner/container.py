"""The generic stage protocol: ordering, deadlines, persistence, progress.

This is the half of the runner that runs *inside* the pinned execution image.
It owns the stage protocol and nothing else - every stage body, and the decision
of which stages exist, comes from the repository.

There is deliberately no adapter import here. The engine's ``scripts/ci/gate.py``
is the engine's own entry point and delegates to :func:`run_stages`, so this
module must stay importable from inside the engine without a cycle.
"""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path

from . import report as reports_module
from .execute import scrub
from .report import utc_now


class StageError(RuntimeError):
    """A stage failed, or the run did not leave its inputs as it found them."""


class ContainerError(RuntimeError):
    """The container did not finish the run it was asked to perform."""

    def __init__(self, message: str, exit_code: int | None = None):
        super().__init__(message)
        self.exit_code = exit_code


def stage_timeout(signum, frame):
    raise TimeoutError("gate stage exceeded the configured deadline")


def save_report(reports: Path, report: dict) -> None:
    """Persist the report in whatever state currently holds."""
    reports_module.save(reports, report)


def progress_event(reports: Path, event: str, **fields) -> None:
    reports_module.progress_event(reports, event, **fields)


def _artifacts(reports: Path, before: set[str]) -> list[str]:
    if not reports.exists():
        return []
    return sorted(
        name for name in set(os.listdir(reports)) - before if name != reports_module.PROGRESS_NAME
    )


def _finalize(stage: dict, started: float, before: set[str], reports: Path, report: dict) -> None:
    """Stamp timing and artifacts, then persist whatever state currently holds."""
    stage["seconds"] = round(time.monotonic() - started, 2)
    stage["finished_at"] = utc_now()
    stage["artifacts"] = _artifacts(reports, before)
    save_report(reports, report)


def _run_stage(reports: Path, report: dict, steps: dict, stage: dict, timeout: int) -> None:
    started = time.monotonic()
    before = set(os.listdir(reports)) if reports.exists() else set()
    stage.update(status="running", started_at=utc_now())
    save_report(reports, report)
    progress_event(reports, "stage_started", stage=stage["name"])
    print(f"START {stage['name']}", flush=True)
    try:
        signal.alarm(timeout)
        stage["details"] = steps[stage["name"]]() or {}
        stage["status"] = "pass"
    except BaseException as exc:
        signal.alarm(0)
        stage.update(status="fail", error=scrub(f"{type(exc).__name__}: {exc}"))
        _finalize(stage, started, before, reports, report)
        # The failure report is on disk before the event points at it, so a
        # crash between the two still leaves a consistent scene.
        progress_event(
            reports, "stage_failed", failed_stage=stage["name"], error=stage["error"],
            report=str(reports / reports_module.REPORT_NAME), command_log_paths=stage["artifacts"],
        )
        raise
    signal.alarm(0)
    _finalize(stage, started, before, reports, report)
    progress_event(reports, "stage_passed", stage=stage["name"], seconds=stage["seconds"])
    print(f"PASS {stage['name']} ({stage['seconds']} s)", flush=True)


def run_stages(reports: Path, steps: dict, report: dict, timeout: int) -> dict:
    """Run every stage in the given order, stopping at the first failure.

    ``steps`` is an ordered mapping; its order *is* the stage contract. Later
    stages stay ``not_run`` because the failing stage raises.
    """
    signal.signal(signal.SIGALRM, stage_timeout)
    if not report.get("stages"):
        report["stages"] = [{"name": name, "status": "not_run"} for name in steps]
    progress_event(reports, "gate_started", commit=report.get("commit"), stages=list(steps))
    for stage in report["stages"]:
        _run_stage(Path(reports), report, steps, stage, timeout)
    return report


def _terminal(reports: Path, report: dict, status: str, exit_code: int, **fields) -> dict:
    """Persist the terminal state before anything announces it.

    A progress consumer reads the report named by the event, so the event must
    never point at a report that still says ``running``. Saving first also means
    a crash between the two leaves a consistent scene rather than a pass that
    was never written down.
    """
    report.update(status=status, exit_code=exit_code, finished_at=utc_now(), **fields)
    save_report(reports, report)
    return report


def finalize(root: Path, reports: Path, report: dict, *, input_hashes, is_dirty) -> dict:
    """Prove the run did not move its own inputs, then declare success.

    Pass is announced only after stage success, input integrity and a clean
    snapshot all hold - never a false pass in ``progress.jsonl``.
    """
    if report["inputs"] != input_hashes(Path(root)):
        raise StageError("checks changed tracked inputs")
    if is_dirty(Path(root)):
        raise StageError("checks left the execution snapshot dirty")
    _terminal(Path(reports), report, "pass", 0)
    progress_event(Path(reports), "gate_passed")
    return report


def fail(reports: Path, report: dict, exc: BaseException) -> dict:
    """Persist the failure, then point the progress stream at the persisted report."""
    _terminal(Path(reports), report, "fail", 1, error=scrub(f"{type(exc).__name__}: {exc}"))
    progress_event(
        Path(reports), "gate_failed", error=report["error"],
        report=str(Path(reports) / reports_module.REPORT_NAME),
    )
    print(report["error"], flush=True)
    return report


def _emitted_events(reports: Path) -> list[str]:
    """The events already durable in the progress stream, ignoring torn lines."""
    path = Path(reports) / reports_module.PROGRESS_NAME
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        try:
            events.append(json.loads(line).get("event"))
        except json.JSONDecodeError:
            continue
    return events


def finalize_host_failure(reports: Path, skeleton: dict, exc: BaseException) -> None:
    """Complete a report the container did not finish, then announce the failure.

    The container's own terminal state is authoritative when it exists: a stage
    failure it recorded keeps its error, stages and logs. The host only adds what
    is missing, and replaces a pass its own verification refused.

    The report and the event are completed independently. ``container.fail``
    saves before it announces, so a failed announcement leaves a terminal report
    with no terminal event; returning early in that case would strand every
    subscriber. The report is on disk before the event points at it, and an
    event that is already there is never repeated.
    """
    try:
        current = reports_module.load(reports)
    except reports_module.ReportError:
        current = dict(skeleton)
    if not (current.get("status") == "fail" and current.get("finished_at")):
        exit_code = getattr(exc, "exit_code", None)
        current.update(status="fail", finished_at=utc_now(),
                       exit_code=exit_code if exit_code is not None else 1,
                       error=scrub(f"{type(exc).__name__}: {exc}"))
        reports_module.save(reports, current)
    if "gate_failed" in _emitted_events(reports):
        return
    reports_module.progress_event(reports, "gate_failed", error=current.get("error", ""),
                                  report=str(Path(reports) / reports_module.REPORT_NAME))
