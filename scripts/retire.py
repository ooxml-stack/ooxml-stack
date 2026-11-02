"""Workspace retire gc: ledger-driven TTL retirement plus a tripwire.

CLEANUP-TODO B1.1: every artifact should get its death date at creation.
The retire-registry OPC extension registers executor run artifacts with
TTLs into <workspace>/.delivery-evidence/retire-registry/registry.jsonl;
this script is the consumer that reclaims them on schedule.

Execution scope (v1):
- Delete files whose ledger entries expired (registered run artifacts past
  their expires_at).
- Compact the ledger once it exceeds --compact-threshold non-empty lines,
  dropping expired entries. Below the threshold the ledger stays
  append-only; this script is the compaction owner.
- Everything else is report-only: unregistered .delivery-evidence content
  (tripwire), ~/.opc sessions, .archive-backups and .worktrees are
  inventoried and proposed for the matching CLEANUP-TODO items instead of
  being touched.

Safety invariants:
- --dry-run is the default; --execute is required for any destructive step.
- The ledger directory is infrastructure and never a deletion target.
- Symlinks are never followed or deleted (the extension does not register
  symlinks; if one ever appears in the ledger, retirement skips it loudly).
- Nothing inside a .git directory is touched.
- Deletions are confined to managed roots (the workspace, ~/.opc/sessions
  and any --managed-root); entries pointing elsewhere are skipped loudly.
- Run artifacts inside a flow that is not completed are skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LEDGER_DIR_PARTS = (".delivery-evidence", "retire-registry")
DEFAULT_COMPACT_THRESHOLD = 5000
DEFAULT_SESSION_ARCHIVE_DAYS = 30
MAX_LISTED = 50

LIFETIME_TABLE = {
    "executor run artifacts (ledger TTL)": "automated: delete expired ledger entries",
    ".delivery-evidence task evidence": "tripwire + manual sweep (CLEANUP-TODO B1)",
    ".archive-backups": "report-only -> compress/move to cold storage (B2)",
    ".worktrees": "report-only -> per-item retirement review (B3)",
    "LFS caches": "manual prune after push verification (A4)",
    "~/.opc sessions": "report-only -> archive completed flows (manual until v2)",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_workspace(explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve(strict=True)
        if not (root / ".delivery-evidence").is_dir():
            raise ValueError(f"--workspace has no .delivery-evidence: {root}")
        return root
    for parent in Path(__file__).resolve().parents:
        if (parent / ".delivery-evidence").is_dir():
            return parent
    raise ValueError("no workspace found; pass --workspace explicitly")


def ledger_paths(workspace: Path, override: str | None) -> tuple[Path, Path]:
    ledger_dir = workspace.joinpath(*LEDGER_DIR_PARTS)
    registry = (
        Path(override).expanduser().resolve() if override else ledger_dir / "registry.jsonl"
    )
    return ledger_dir, registry


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


def _parse_expires(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _flow_status(path: Path, max_up: int = 6) -> str | None:
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
        path = Path(path_value)
        if path_value in seen:
            skipped.append({"path": path_value, "reason": "duplicate-entry"})
            continue
        seen.add(path_value)
        expires = _parse_expires(rec.get("expires_at"))
        if expires is None:
            skipped.append({"path": path_value, "reason": "bad-expires-at"})
            continue
        if expires > now:
            skipped.append({"path": path_value, "reason": "not-expired"})
            continue
        if not path.is_absolute():
            skipped.append({"path": path_value, "reason": "relative-path"})
            continue
        if any(part == ".git" for part in path.parts):
            skipped.append({"path": path_value, "reason": "git-internals-refused"})
            continue
        if path == ledger_dir or ledger_dir in path.parents:
            skipped.append({"path": path_value, "reason": "ledger-exempt"})
            continue
        if not any(path.is_relative_to(root) for root in managed_roots):
            skipped.append({"path": path_value, "reason": "outside-managed-roots"})
            continue
        if path.is_symlink():
            skipped.append({"path": path_value, "reason": "symlink-refused"})
            continue
        if not path.exists():
            missing.append({"path": path_value, "expires_at": rec.get("expires_at")})
            continue
        if not path.is_file():
            skipped.append({"path": path_value, "reason": "not-regular-file"})
            continue
        status = _flow_status(path)
        if status is not None and status != "completed":
            skipped.append({"path": path_value, "reason": "session-not-completed"})
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


def plan_compaction(raw: list[str], now: datetime, threshold: int) -> dict:
    kept: list[str] = []
    dropped = 0
    for line in raw:
        try:
            rec = json.loads(line)
        except ValueError:
            dropped += 1
            continue
        expires = _parse_expires(rec.get("expires_at") if isinstance(rec, dict) else None)
        if expires is not None and expires <= now:
            dropped += 1
            continue
        kept.append(line)
    return {
        "line_count": len(raw),
        "threshold": threshold,
        "would_compact": len(raw) > threshold,
        "kept_lines": len(kept),
        "dropped_expired_or_torn": dropped,
        "kept_raw": kept,
    }


def _tree_size(root: Path) -> int:
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
            payload = {
                "created_at": _iso(now),
                "grandfathered_count": len(rel_paths),
                "grandfathered": rel_paths,
            }
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            status = state.get("status")
        except (OSError, ValueError):
            report["unreadable"] += 1
            continue
        if status == "completed":
            report["completed"] += 1
        elif status == "in_progress":
            report["in_progress"] += 1
        else:
            report["other_status"] += 1
        if status != "completed":
            continue
        try:
            mtime = state_path.stat().st_mtime
        except OSError:
            continue
        if mtime > cutoff:
            continue
        if len(report["archive_candidates"]) >= MAX_LISTED:
            report["truncated"] = True
            continue
        flow_dir = state_path.parent
        report["archive_candidates"].append(
            {
                "flow": str(flow_dir.relative_to(root)),
                "age_days": round(max(0.0, (now.timestamp() - mtime) / 86400), 1),
                "last_activity": datetime.fromtimestamp(mtime, timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "bytes": _tree_size(flow_dir),
            }
        )
    return report


def static_inventory(workspace: Path) -> dict:
    report: dict = {}
    backups = workspace / ".archive-backups"
    if backups.is_dir():
        items = sorted(p.name for p in backups.iterdir())
        report["archive_backups"] = {
            "path": str(backups),
            "top_level_items": len(items),
            "bytes": _tree_size(backups),
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


def _execute_deletions(
    delete: list[dict], managed_roots: list[Path]
) -> tuple[list[dict], list[dict], list[str]]:
    removed: list[dict] = []
    failed: list[dict] = []
    empty_dirs: list[str] = []
    protected = {str(Path(root)) for root in managed_roots}
    for item in delete:
        path = Path(item["path"])
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError as exc:
            failed.append({"path": item["path"], "error": str(exc)})
            continue
        removed.append({**item, "bytes": size})
        parent = path.parent
        for _ in range(3):
            if str(parent) in protected or parent == parent.parent:
                break
            try:
                parent.rmdir()
            except OSError:
                break
            empty_dirs.append(str(parent))
            parent = parent.parent
    return removed, failed, empty_dirs


def _write_manifest(ledger_dir: Path, report: dict, now: datetime) -> Path:
    manifest_dir = ledger_dir / "gc-manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_dir / f"gc-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


def run_gc(
    workspace: Path,
    mode: str,
    now: datetime,
    compact_threshold: int,
    session_archive_days: int,
    extra_managed_roots: list[str],
    registry_override: str | None,
) -> dict:
    ledger_dir, registry = ledger_paths(workspace, registry_override)
    managed_roots = [
        workspace,
        Path.home() / ".opc" / "sessions",
        *(Path(root).expanduser().resolve() for root in extra_managed_roots),
    ]
    entries, torn, raw = load_ledger(registry)
    delete, skipped, missing = plan_deletions(entries, managed_roots, ledger_dir, now)
    compaction = plan_compaction(raw, now, compact_threshold)
    ledger_path_set = {
        rec["path"] for rec in entries if isinstance(rec.get("path"), str)
    }
    tripwire = tripwire_report(
        workspace, ledger_dir, ledger_path_set, ledger_dir / "tripwire-baseline.json", mode, now
    )
    report: dict = {
        "mode": mode,
        "workspace": str(workspace),
        "started_at": _iso(now),
        "ledger": {
            "path": str(registry),
            "entries": len(entries),
            "torn_lines": torn,
            "exists": registry.is_file(),
        },
        "deletions": {
            "candidates": delete,
            "skipped": skipped,
            "already_missing": missing,
        },
        "compaction": {k: v for k, v in compaction.items() if k != "kept_raw"},
        "tripwire": tripwire,
        "sessions": session_inventory(now, session_archive_days),
        "static": static_inventory(workspace),
        "lifetime_table": LIFETIME_TABLE,
    }
    if mode != "execute":
        return report
    removed, failed, empty_dirs = _execute_deletions(delete, managed_roots)
    report["deletions"]["removed"] = removed
    report["deletions"]["failed"] = failed
    report["deletions"]["removed_empty_dirs"] = empty_dirs
    report["bytes_reclaimed"] = sum(item["bytes"] or 0 for item in removed)
    if compaction["would_compact"]:
        kept_lines = [
            line
            for line in compaction["kept_raw"]
        ]
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(
            ("\n".join(kept_lines) + "\n") if kept_lines else "", encoding="utf-8"
        )
        report["compaction"]["executed"] = True
    manifest_path = _write_manifest(ledger_dir, report, now)
    report["manifest_path"] = str(manifest_path)
    return report


def _print_summary(report: dict) -> None:
    mode = report["mode"]
    deletions = report["deletions"]
    print(f"retire [{mode}] workspace={report['workspace']}")
    print(
        f"  ledger: entries={report['ledger']['entries']} "
        f"torn={report['ledger']['torn_lines']}"
    )
    if mode == "execute":
        print(
            f"  removed={len(deletions.get('removed', []))} "
            f"failed={len(deletions.get('failed', []))} "
            f"reclaimed_bytes={report.get('bytes_reclaimed', 0)}"
        )
    else:
        print(f"  delete candidates={len(deletions['candidates'])}")
    print(
        f"  compaction: would_compact={report['compaction']['would_compact']} "
        f"lines={report['compaction']['line_count']}"
    )
    tw = report["tripwire"]
    if tw.get("baseline_missing"):
        print(
            f"  tripwire: baseline missing; grandfathered_candidates="
            f"{tw.get('grandfathered_candidates', 0)}"
        )
    else:
        print(f"  tripwire: alarms={tw.get('alarms_total', 0)}")
    sessions = report["sessions"]
    print(
        f"  sessions: total={sessions['flows_total']} "
        f"completed={sessions['completed']} in_progress={sessions['in_progress']} "
        f"archive_candidates={len(sessions['archive_candidates'])}"
    )
    if mode == "execute":
        print(f"  manifest: {report.get('manifest_path')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", help="workspace root (default: auto-detect)")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="perform deletions and compaction (default: dry-run)",
    )
    parser.add_argument("--json", dest="as_json", action="store_true", help="print full JSON report")
    parser.add_argument("--compact-threshold", type=int, default=DEFAULT_COMPACT_THRESHOLD)
    parser.add_argument("--session-archive-days", type=int, default=DEFAULT_SESSION_ARCHIVE_DAYS)
    parser.add_argument(
        "--managed-root",
        action="append",
        default=[],
        help="extra root under which ledger deletions are allowed (repeatable)",
    )
    parser.add_argument("--registry", help="override ledger path (default: workspace ledger)")
    parser.add_argument(
        "--fail-on-alarm",
        action="store_true",
        help="exit 3 when the tripwire reports unregistered content",
    )
    args = parser.parse_args(argv)
    try:
        workspace = find_workspace(args.workspace)
        report = run_gc(
            workspace,
            "execute" if args.execute else "dry-run",
            _utc_now(),
            args.compact_threshold,
            args.session_archive_days,
            args.managed_root,
            args.registry,
        )
    except (OSError, ValueError) as exc:
        print(f"retire refused: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        _print_summary(report)
    if args.fail_on_alarm and report["tripwire"].get("alarms_total", 0) > 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
