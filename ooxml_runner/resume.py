"""Verified selective resume from a durable failed report.

Resume is deliberately conservative: every identity that can change a stage
result must match before any stage is reused. The reusable unit is the contiguous
successful prefix before the first failed stage. The failed stage and all later
stages rerun. This keeps the final report a complete all-stage union.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import report as report_module

RESUME_NAME = "resume.json"
RESUME_SCHEMA_VERSION = 1


class ResumeError(report_module.ReportError):
    """The prior report cannot safely certify any part of this run."""


def _same(label: str, previous: Any, current: Any) -> None:
    if previous != current:
        raise ResumeError(f"resume {label} differs from the requested run")


def _identity(previous: dict[str, Any], current: dict[str, Any]) -> None:
    for field in ("repository", "commit", "runner", "image", "inputs", "binding"):
        _same(field, previous.get(field), current.get(field))
    previous_plan = previous.get("plan") or {}
    current_plan = current.get("plan") or {}
    for field in ("sha256", "inputs_digest"):
        _same(f"plan.{field}", previous_plan.get(field), current_plan.get(field))


def _stages(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    old = previous.get("stages")
    new = current.get("stages")
    if not isinstance(old, list) or not isinstance(new, list):
        raise ResumeError("resume report has no stage list")
    if [item.get("name") if isinstance(item, dict) else None for item in old] != [
        item.get("name") if isinstance(item, dict) else None for item in new
    ]:
        raise ResumeError("resume stage contract differs from the requested run")
    return old


def _failed_nodes(report_path: Path, prior: dict[str, Any]) -> list[str]:
    pytest_path = report_path.parent / "pytest.json"
    try:
        payload = json.loads(pytest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    nodes = {
        row.get("nodeid")
        for row in results
        if isinstance(row, dict)
        and row.get("outcome") == "failed"
        and isinstance(row.get("nodeid"), str)
    }
    if not nodes:
        return []
    collected = payload.get("collected")
    if not isinstance(collected, list) or not set(nodes).issubset(set(collected)):
        raise ResumeError("prior pytest receipt has failed nodes outside its collected union")
    return sorted(nodes)


def prepare(
    previous: dict[str, Any], current: dict[str, Any], source_report: Path, reports: Path
) -> dict[str, Any]:
    """Apply the verified reusable prefix and persist the focused resume plan."""
    if previous.get("schema_version") != report_module.REPORT_SCHEMA_VERSION:
        raise ResumeError("resume report schema differs from the runner")
    _identity(previous, current)
    old_stages = _stages(previous, current)
    first_failure = None
    for index, stage in enumerate(old_stages):
        if stage.get("status") != "pass":
            first_failure = index
            break
    if first_failure is None:
        raise ResumeError("resume report is already a complete pass")
    current_stages = current["stages"]
    reused = []
    for index in range(first_failure):
        expected = current_stages[index]
        old = old_stages[index]
        if old.get("status") != "pass":
            raise ResumeError(f"resume stage {expected.get('name')!r} is not a pass")
        expected.update(
            status="pass",
            reused=True,
            reused_from=source_report.parent.as_posix(),
            details=old.get("details", {}),
            artifacts=list(old.get("artifacts") or []),
        )
        reused.append(expected["name"])
    failed_stage = current_stages[first_failure]["name"]
    plan = {
        "schema_version": RESUME_SCHEMA_VERSION,
        "source_report": str(source_report),
        "source_attempt": previous.get("started_at"),
        "failed_stage": failed_stage,
        "reused_stages": reused,
        "rerun_stages": [stage["name"] for stage in current_stages[first_failure:]],
        "failed_nodes": _failed_nodes(source_report, previous),
    }
    current["resume"] = plan
    report_module.save(reports, current)
    (Path(reports) / RESUME_NAME).write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan
