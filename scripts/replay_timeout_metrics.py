"""Shared replay-timeout ledger counters."""
from __future__ import annotations

from typing import Any


def replay_timeout_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    package_scope = [row for row in rows if not row.get("operation_id")]
    operation_scope = [row for row in rows if row.get("operation_id")]
    return {
        "known_replay_timeout_package_count": len({str(row.get("package_id", "")) for row in rows if row.get("package_id")}),
        "known_replay_timeout_entry_count": len(rows),
        "known_replay_timeout_package_scope_count": len(package_scope),
        "known_replay_timeout_operation_scope_count": len(operation_scope),
    }
