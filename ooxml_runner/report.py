"""The execution report: schema, persistence and generic verification.

The report extends the engine's existing shape rather than replacing it, so the
historical stage contract keeps working while the new identity fields (runner
version, plan identity, binding) become verifiable facts.

Verification is split deliberately:

* this module checks the *generic* contract - the report belongs to the
  requested repository, commit, runner and plan, and its stage list is exactly
  the adapter's declared stage list, all passing;
* the adapter checks the *repository-specific* contract - image digest, input
  hashes, governance and acceptance rules.

A report never passes on a self-reported ``status`` alone.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from . import PROGRESS_SCHEMA_VERSION, REPORT_SCHEMA_VERSION
from .execute import scrub

REPORT_NAME = "report.json"
PROGRESS_NAME = "progress.jsonl"


class ReportError(RuntimeError):
    """The report is missing, malformed, or does not describe this execution."""


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def new_report(
    *, repository: str, commit: str, runner: dict, plan: dict, binding: dict, image: str, inputs: dict
) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "running",
        "repository": repository,
        "commit": commit,
        "runner": {"commit": runner.get("commit"), "source_sha256": runner.get("source_sha256")},
        "plan": dict(plan),
        "binding": dict(binding),
        "image": image,
        "inputs": dict(inputs),
        "started_at": utc_now(),
        "finished_at": None,
        "exit_code": None,
        "stages": [],
    }


def save(reports: Path, report: dict[str, Any]) -> None:
    """Persist atomically; the temporary file never becomes the visible report."""
    reports = Path(reports)
    reports.mkdir(parents=True, exist_ok=True)
    temporary = reports / f"{REPORT_NAME}.tmp"
    temporary.write_text(scrub(json.dumps(report, indent=2)) + "\n", encoding="utf-8")
    temporary.replace(reports / REPORT_NAME)


def load(path: Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_dir():
        path = path / REPORT_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReportError(f"report is unreadable: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReportError(f"report is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReportError("report must be a JSON object")
    return payload


def progress_event(reports: Path, event: str, **fields: Any) -> None:
    """Append one durable progress row; a crash keeps every flushed line."""
    row = {"schema_version": PROGRESS_SCHEMA_VERSION, "timestamp": utc_now(), "event": event, **fields}
    path = Path(reports) / PROGRESS_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as progress:
        progress.write(scrub(json.dumps(row)) + "\n")
        progress.flush()


def _expected_stage_names(expected: dict[str, Any]) -> list[str]:
    names = expected.get("stages")
    if not names:
        raise ReportError("verification requires the adapter's declared stage list")
    return list(names)


def verify_generic(report: dict[str, Any], expected: dict[str, Any]) -> None:
    """Check the report against caller-supplied expectations, not its own claims."""
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ReportError(f"unsupported report schema {report.get('schema_version')!r}")
    for field in ("repository", "commit"):
        if report.get(field) != expected.get(field):
            raise ReportError(
                f"report {field} {report.get(field)!r} does not match requested {expected.get(field)!r}"
            )
    if (report.get("runner") or {}).get("commit") != expected.get("runner_commit"):
        raise ReportError("report runner commit does not match the requested runner commit")
    plan = report.get("plan") or {}
    if plan.get("sha256") != expected.get("plan_sha256"):
        raise ReportError("report plan sha256 does not match the requested plan file")
    if plan.get("inputs_digest") != expected.get("inputs_digest"):
        raise ReportError("report inputs_digest does not match the requested plan")
    if report.get("status") != "pass":
        raise ReportError(f"report is not a pass: {report.get('status')!r}")
    if report.get("exit_code") != 0:
        raise ReportError(f"report exit_code is {report.get('exit_code')!r}, not 0")
    stages = report.get("stages") or []
    if not isinstance(stages, list):
        raise ReportError("report stages must be a list")
    names = [stage.get("name") if isinstance(stage, dict) else None for stage in stages]
    if names != _expected_stage_names(expected):
        raise ReportError("report has missing, duplicate, or unexpected stages")
    for stage in stages:
        if stage.get("status") != "pass":
            raise ReportError(f"stage {stage.get('name')!r} is {stage.get('status')!r}, not pass")