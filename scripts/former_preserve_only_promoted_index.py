from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TargetKey = tuple[str, str, str, str]
ALIAS_REASON = "duplicate package/operation/target/attribute evidence; retained for audit but not counted as independent semantic-editable row"


def promoted_index(rows_path: Path) -> tuple[set[str], set[TargetKey]]:
    source_ids: set[str] = set()
    targets: set[TargetKey] = set()
    for row in _passed_rows(rows_path):
        source_ids.add(row.get("source_row_id", ""))
        key = _payload_key(row)
        if key not in targets:
            targets.add(key)
    return source_ids, targets


def alias_operation_count(rows_path: Path) -> int:
    return alias_operation_count_from_rows(_passed_rows(rows_path))


def alias_operation_count_from_rows(rows: list[dict[str, Any]]) -> int:
    count = 0
    targets: set[TargetKey] = set()
    for row in rows:
        key = _payload_key(row)
        if key in targets:
            count += 1
        else:
            targets.add(key)
    return count


def split_alias_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    promoted: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    targets: dict[TargetKey, dict[str, Any]] = {}
    for row in rows:
        key = _payload_key(row)
        if row.get("pass") is True and key in targets:
            aliases.append(_alias_row(row, targets[key]))
        else:
            promoted.append(row)
            if row.get("pass") is True:
                targets[key] = row
    return promoted, aliases


def _alias_row(row: dict[str, Any], original: dict[str, Any]) -> dict[str, Any]:
    alias = dict(row)
    alias["alias_reason"] = ALIAS_REASON
    alias["alias_of_row_id"] = original.get("row_id", "")
    alias["alias_of_source_row_id"] = original.get("source_row_id", "")
    return alias


def deduped_operation_count(rows: list[dict[str, Any]]) -> int:
    return len({_payload_key(row) for row in rows if row.get("pass") is True})


def row_target_key(row: dict[str, Any]) -> TargetKey:
    target = f"{row.get('part_name', '')}::{row.get('operation_target_selector') or row.get('selector', '')}"
    return (row.get("package_id", ""), row.get("operation_id", ""), target, _target_attribute(row))


def _target_attribute(row: dict[str, Any]) -> str:
    if row.get("operation_id") == "vml.formula.eqn.set_value":
        return ""
    return row.get("attribute_name", "")


def _payload_key(row: dict[str, Any]) -> TargetKey:
    params = row.get("operation_params", {})
    return (
        row.get("package_id", ""),
        row.get("operation_id", ""),
        row.get("operation_target", ""),
        params.get("attribute_name", ""),
    )


def _passed_rows(rows_path: Path) -> list[dict[str, Any]]:
    if not rows_path.exists():
        return []
    rows = []
    for line in rows_path.read_text(encoding="utf-8").splitlines():
        row = _loads(line)
        if row.get("pass") is True:
            rows.append(row)
    return rows


def _loads(line: str) -> dict[str, Any]:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {}
