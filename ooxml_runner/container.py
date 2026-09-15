"""The generic stage protocol: ordering, deadlines, persistence, progress.

This is the half of the runner that runs *inside* the pinned execution image.
It owns the stage protocol and nothing else - every stage body, and the decision
of which stages exist, comes from the repository.

There is deliberately no adapter import here. The engine's ``scripts/ci/gate.py``
is the engine's own entry point and delegates to :func:`run_stages`, so this
module must stay importable from inside the engine without a cycle.
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

from . import report as reports_module
from .execute import scrub
from .report import utc_now


class StageError(RuntimeError):
    """A stage failed, or the run did not leave its inputs as it found them."""


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


def finalize(root: Path, reports: Path, report: dict, *, input_hashes, is_dirty) -> dict:
    """Prove the run did not move its own inputs, then declare success.

    Pass is announced only after stage success, input integrity and a clean
    snapshot all hold - never a false pass in ``progress.jsonl``.
    """
    if report["inputs"] != input_hashes(Path(root)):
        raise StageError("checks changed tracked inputs")
    if is_dirty(Path(root)):
        raise StageError("checks left the execution snapshot dirty")
    report["status"] = "pass"
    report["exit_code"] = 0
    progress_event(Path(reports), "gate_passed")
    return report


def fail(reports: Path, report: dict, exc: BaseException) -> dict:
    """Record a failure in the report and the progress stream, then persist."""
    report.update(status="fail", exit_code=1, error=scrub(f"{type(exc).__name__}: {exc}"))
    progress_event(
        Path(reports), "gate_failed", error=report["error"],
        report=str(Path(reports) / reports_module.REPORT_NAME),
    )
    print(report["error"], flush=True)
    return report