"""Report-only inventories: tripwire, OPC sessions, backups, worktrees."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

MAX_LISTED = 50


def tree_size(root: Path) -> int:
    total = 0
    for walk_root, _dirs, files in os.walk(root, followlinks=False):
        for name in files:
            try:
                st = (Path(walk_root) / name).lstat()
            except OSError:
                continue
            total += st.st_size
    return total


def scan_unregistered(
    workspace: Path, ledger_dir: Path, ledger_path_set: set[str]
) -> tuple[list[Path], int]:
    evidence = workspace / ".delivery-evidence"
    unregistered: list[Path] = []
    symlinks = 0
    if not evidence.is_dir():
        return unregistered, symlinks
    for walk_root, dirs, files in os.walk(evidence, followlinks=False):
        root_path = Path(walk_root)
        dirs[:] = [d for d in dirs if (root_path / d) != ledger_dir]
        for name in files:
            p = root_path / name
            if p.is_symlink():
                symlinks += 1
                continue
            if str(p) in ledger_path_set:
                continue
            unregistered.append(p)
    return unregistered, symlinks


def tripwire_report(
    workspace: Path,
    ledger_dir: Path,
    ledger_path_set: set[str],
    baseline_path: Path,
    mode: str,
    now: datetime,
) -> dict:
    unregistered, symlinks = scan_unregistered(workspace, ledger_dir, ledger_path_set)
    rel_paths = sorted(str(p.relative_to(workspace)) for p in unregistered)
    report: dict = {
        "evidence_root": str(workspace / ".delivery-evidence"),
        "unregistered_total": len(rel_paths),
        "symlinks_skipped": symlinks,
        "note": "ledger covers executor-phase artifacts only; .delivery-evidence "
        "content is guarded by this tripwire, not by the ledger",
    }
    if not baseline_path.is_file():
        report["baseline_missing"] = True
        report["grandfathered_candidates"] = len(rel_paths)
        if mode == "execute":
            _write_baseline(baseline_path, rel_paths, now)
            report["baseline_created"] = True
        return report
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        known = set(baseline.get("grandfathered", []))
    except (OSError, ValueError):
        report["baseline_unreadable"] = True
        return report
    alarms = [r for r in rel_paths if r not in known]
    report.update(
        {
            "baseline_created_at": baseline.get("created_at"),
            "grandfathered": len(known),
            "alarms_total": len(alarms),
            "alarms": alarms[:MAX_LISTED],
            "truncated": len(alarms) > MAX_LISTED,
            "refresh_hint": "re-grandfather with --baseline-refresh after manual disposition",
        }
    )
    return report


def _write_baseline(baseline_path: Path, rel_paths: list[str], now: datetime) -> None:
    payload = {
        "created_at": datetime.isoformat(now).replace("+00:00", "Z"),
        "grandfathered_count": len(rel_paths),
        "grandfathered": rel_paths,
    }
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def session_inventory(now: datetime, archive_days: int) -> dict:
    root = Path.home() / ".opc" / "sessions"
    report: dict = {
        "root": str(root),
        "flows_total": 0,
        "completed": 0,
        "in_progress": 0,
        "other_status": 0,
        "unreadable": 0,
        "archive_after_days": archive_days,
        "archive_candidates": [],
        "truncated": False,
        "proposed_action": "archive completed flows; in_progress flows untouched",
    }
    if not root.is_dir():
        return report
    cutoff = now.timestamp() - archive_days * 86400
    for state_path in sorted(root.glob("*/*/flow-state.json")):
        report["flows_total"] += 1
        status = _read_status(state_path, report)
        if status is None:
            continue
        if status != "completed":
            continue
        _add_archive_candidate(state_path, report, now, cutoff)
    return report


def _read_status(state_path: Path, report: dict) -> str | None:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        status = state.get("status")
    except (OSError, ValueError):
        report["unreadable"] += 1
        return None
    if status == "completed":
        report["completed"] += 1
    elif status == "in_progress":
        report["in_progress"] += 1
    else:
        report["other_status"] += 1
    return status if isinstance(status, str) else None


def _add_archive_candidate(
    state_path: Path, report: dict, now: datetime, cutoff: float
) -> None:
    try:
        mtime = state_path.stat().st_mtime
    except OSError:
        return
    if mtime > cutoff:
        return
    if len(report["archive_candidates"]) >= MAX_LISTED:
        report["truncated"] = True
        return
    flow_dir = state_path.parent
    report["archive_candidates"].append(
        {
            "flow": str(flow_dir.relative_to(Path(report["root"]))),
            "age_days": round(max(0.0, (now.timestamp() - mtime) / 86400), 1),
            "last_activity": datetime.fromtimestamp(mtime, timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "bytes": tree_size(flow_dir),
        }
    )


def static_inventory(workspace: Path) -> dict:
    report: dict = {}
    backups = workspace / ".archive-backups"
    if backups.is_dir():
        items = sorted(p.name for p in backups.iterdir())
        report["archive_backups"] = {
            "path": str(backups),
            "top_level_items": len(items),
            "bytes": tree_size(backups),
            "proposed_action": "compress or move to cold storage (B2)",
        }
    worktrees = workspace / ".worktrees"
    if worktrees.is_dir():
        names = sorted(p.name for p in worktrees.iterdir() if p.is_dir())
        report["worktrees"] = {
            "path": str(worktrees),
            "entries": names,
            "proposed_action": "per-item retirement review (B3)",
        }
    return report
