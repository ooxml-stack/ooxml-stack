"""Ledger loading and deletion planning for the retire gc."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

LEDGER_DIR_PARTS = (".delivery-evidence", "retire-registry")


def parse_expires(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_ledger(registry: Path) -> tuple[list[dict], int, list[str]]:
    """Return (parsed entries, torn line count, raw non-empty lines)."""
    entries: list[dict] = []
    raw: list[str] = []
    torn = 0
    try:
        text = registry.read_text(encoding="utf-8")
    except FileNotFoundError:
        return entries, 0, []
    for line in text.splitlines():
        if not line.strip():
            continue
        raw.append(line)
        try:
            rec = json.loads(line)
        except ValueError:
            torn += 1
            continue
        if isinstance(rec, dict):
            entries.append(rec)
        else:
            torn += 1
    return entries, torn, raw


def flow_status(path: Path, max_up: int = 6) -> str | None:
    """Find the nearest flow-state.json status above an artifact path."""
    cur = path.parent
    for _ in range(max_up):
        marker = cur / "flow-state.json"
        if marker.is_file():
            try:
                state = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            status = state.get("status")
            return status if isinstance(status, str) else None
        if cur == cur.parent:
            return None
        cur = cur.parent
    return None


def _deletion_reason(
    path: Path,
    expires: datetime | None,
    managed_roots: list[Path],
    ledger_dir: Path,
    now: datetime,
) -> str | None:
    """Return a refusal reason, 'already-missing', or None when deletable."""
    if expires is None:
        return "bad-expires-at"
    if expires > now:
        return "not-expired"
    if not path.is_absolute():
        return "relative-path"
    if any(part == ".git" for part in path.parts):
        return "git-internals-refused"
    if path == ledger_dir or ledger_dir in path.parents:
        return "ledger-exempt"
    if not any(path.is_relative_to(root) for root in managed_roots):
        return "outside-managed-roots"
    if path.is_symlink():
        return "symlink-refused"
    if not path.exists():
        return "already-missing"
    if not path.is_file():
        return "not-regular-file"
    status = flow_status(path)
    if status is not None and status != "completed":
        return "session-not-completed"
    return None


def plan_deletions(
    entries: list[dict],
    managed_roots: list[Path],
    ledger_dir: Path,
    now: datetime,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Split expired entries into (delete candidates, skips, already-missing)."""
    delete: list[dict] = []
    skipped: list[dict] = []
    missing: list[dict] = []
    seen: set[str] = set()
    for rec in entries:
        path_value = rec.get("path")
        if not isinstance(path_value, str) or not path_value:
            skipped.append({"path": None, "reason": "malformed-entry"})
            continue
        if path_value in seen:
            skipped.append({"path": path_value, "reason": "duplicate-entry"})
            continue
        seen.add(path_value)
        path = Path(path_value)
        expires = parse_expires(rec.get("expires_at"))
        reason = _deletion_reason(path, expires, managed_roots, ledger_dir, now)
        if reason == "already-missing":
            missing.append({"path": path_value, "expires_at": rec.get("expires_at")})
            continue
        if reason is not None:
            skipped.append({"path": path_value, "reason": reason})
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        delete.append(
            {
                "path": path_value,
                "bytes": size,
                "entry_ts": rec.get("ts"),
                "expires_at": rec.get("expires_at"),
                "session": rec.get("session"),
                "node": rec.get("node"),
                "run": rec.get("run"),
            }
        )
    return delete, skipped, missing
