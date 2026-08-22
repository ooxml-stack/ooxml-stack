"""Timeout classification helpers for semantic promotion chunk planning."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from campaign_office_boundary_summary import primary_status


def merge_office_timeout_boundaries(
    office: dict[str, dict[str, Any]], checkpoint_path: Path, root: Path | None = None
) -> dict[str, dict[str, Any]]:
    merged = dict(office)
    for record in _timeout_records(checkpoint_path):
        if not _is_office_timeout(record, root):
            continue
        package = str(record.get("package_id", ""))
        if package:
            merged[package] = _timeout_row(record, merged.get(package, {}))
    return merged


def replay_timeout_packages(checkpoint_path: Path, root: Path | None = None) -> list[dict[str, Any]]:
    records = _checkpoint_records(checkpoint_path)
    canaries = _small_chunk_canaries(records)
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    timeout_packages: set[str] = set()
    for record in records:
        if record.get("status") != "timeout":
            continue
        if _is_office_timeout(record, root):
            continue
        package = str(record.get("package_id", ""))
        if not package:
            continue
        timeout_packages.add(package)
        key = _record_key(record)
        row = rows.setdefault(key, _replay_timeout_row(record))
        row["chunk_ids"].append(str(record.get("chunk_id", "")))
    for key, row in rows.items():
        if key in canaries:
            row.update(canaries[key])
    for key, canary in canaries.items():
        if key[0] in timeout_packages and key not in rows:
            rows[key] = _canary_replay_timeout_row(key, canary)
    return sorted(rows.values(), key=lambda row: row["package_id"])


def _timeout_records(path: Path) -> list[dict[str, Any]]:
    return [row for row in _checkpoint_records(path) if row.get("status") == "timeout"]


def _checkpoint_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("records", [])


def _is_office_timeout(record: dict[str, Any], root: Path | None) -> bool:
    if record.get("stage") == "office_gate":
        return True
    return _office_status(record, root) == "timeout"


def _office_status(record: dict[str, Any], root: Path | None) -> str:
    path = _resolve(record.get("office_result_file", ""), root)
    if not path or not path.exists():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    status = primary_status(data)
    return status if status != "unknown" else str(data.get("status", ""))


def _resolve(value: Any, root: Path | None) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    return path if path.is_absolute() or root is None else root / path


def _timeout_row(record: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    if existing.get("status") not in {"", "pass", "timeout", None}:
        return existing
    return {
        "status": "timeout",
        "office_result": record.get("office_result_file") or f"chunk-promotion-checkpoint.json#{record.get('chunk_id', '')}",
    }


def _replay_timeout_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "package_id": str(record.get("package_id", "")),
        "family": str(record.get("family", "")),
        "operation_id": _single_operation(record),
        "status": "replay_timeout",
        "chunk_ids": [],
        "checkpoint_record": f"chunk-promotion-checkpoint.json#{record.get('chunk_id', '')}",
        "reason": "chunk-level timeout without Office-stage/result timeout evidence",
    }


def _canary_replay_timeout_row(key: tuple[str, str, str], canary: dict[str, Any]) -> dict[str, Any]:
    package, family, operation = key
    return {
        "package_id": package,
        "family": family,
        "operation_id": operation,
        "status": "replay_timeout",
        "chunk_ids": [],
        "checkpoint_record": f"chunk-promotion-checkpoint.json#{canary.get('small_chunk_canary_chunk_id', '')}",
        "reason": "prior package replay timeout; exact operation canary passed",
        **canary,
    }


def _small_chunk_canaries(records: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        if not _is_small_canary(record):
            continue
        key = _record_key(record)
        rows[key] = {
            "slow_replay_state": "small_chunk_canary_passed",
            "small_chunk_canary_chunk_id": record.get("chunk_id", ""),
            "small_chunk_canary_duration_s": record.get("duration_s", 0),
            "small_chunk_canary_rows": record.get("promoted_row_count", 0),
        }
    return rows


def _record_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (str(record.get("package_id", "")), str(record.get("family", "")), _single_operation(record))


def _single_operation(record: dict[str, Any]) -> str:
    operations = record.get("operation_ids") or []
    if record.get("operation_id"):
        return str(record.get("operation_id"))
    return str(operations[0]) if isinstance(operations, list) and len(operations) == 1 else ""


def _is_small_canary(record: dict[str, Any]) -> bool:
    label = str(record.get("label", ""))
    return (
        record.get("status") == "promoted"
        and int(record.get("planned_row_count", 0)) <= 5
        and label.startswith(("canary-", "slow-replay-"))
    )
