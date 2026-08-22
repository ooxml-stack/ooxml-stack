"""Package skip sets for semantic editability chunk planning."""
from __future__ import annotations

from typing import Any


def chunk_plan_skip_packages(
    remaining: dict[str, Any],
    include_boundary: bool,
    canary_package: str = "",
    canary_family: str = "",
    canary_operation: str = "",
) -> dict[str, set[str]]:
    office = set() if include_boundary else _packages(remaining, "known_boundary_packages")
    replay_rows = remaining.get("known_replay_timeout_packages", [])
    replay = {str(row.get("package_id", "")) for row in replay_rows}
    slow = {
        _operation_key(str(row.get("package_id", "")), str(row.get("family", "")), str(row.get("operation_id", "")))
        for row in replay_rows
        if row.get("slow_replay_state") == "small_chunk_canary_passed" and row.get("operation_id")
    }
    if canary_package and canary_family and canary_operation:
        slow.add(_operation_key(canary_package, canary_family, canary_operation))
    return {"known_office_boundary": office, "known_replay_timeout": replay, "slow_replay_allowed": slow}


def package_skip_reason(package_id: str, skip_packages: dict[str, set[str]], family: str = "", operation_id: str = "") -> str:
    if package_id in skip_packages.get("known_office_boundary", set()):
        return "known_office_boundary"
    replay_key = _operation_key(package_id, family, operation_id)
    if package_id in skip_packages.get("known_replay_timeout", set()) and replay_key not in skip_packages.get("slow_replay_allowed", set()):
        return "known_replay_timeout"
    return ""


def _packages(remaining: dict[str, Any], key: str) -> set[str]:
    return {str(row.get("package_id", "")) for row in remaining.get(key, [])}


def _operation_key(package_id: str, family: str, operation_id: str) -> str:
    return f"{package_id}\0{family}\0{operation_id}"
