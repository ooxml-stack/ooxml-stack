"""Report assembly, compaction and execution for the retire gc."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from retire_gc.clock import iso
from retire_gc.inventory import (
    session_inventory,
    static_inventory,
    tripwire_report,
)
from retire_gc.ledger import (
    LEDGER_DIR_PARTS,
    load_ledger,
    parse_expires,
    plan_deletions,
)

DEFAULT_COMPACT_THRESHOLD = 5000

LIFETIME_TABLE = {
    "executor run artifacts (ledger TTL)": "automated: delete expired ledger entries",
    ".delivery-evidence task evidence": "tripwire + manual sweep (CLEANUP-TODO B1)",
    ".archive-backups": "report-only -> compress/move to cold storage (B2)",
    ".worktrees": "report-only -> per-item retirement review (B3)",
    "LFS caches": "manual prune after push verification (A4)",
    "~/.opc sessions": "report-only -> archive completed flows (manual until v2)",
}


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


def plan_compaction(raw: list[str], now: datetime, threshold: int) -> dict:
    kept: list[str] = []
    dropped = 0
    for line in raw:
        try:
            rec = json.loads(line)
        except ValueError:
            dropped += 1
            continue
        expires = parse_expires(rec.get("expires_at") if isinstance(rec, dict) else None)
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
        empty_dirs.extend(_prune_empty_dirs(path.parent, protected))
    return removed, failed, empty_dirs


def _prune_empty_dirs(start: Path, protected: set[str]) -> list[str]:
    removed: list[str] = []
    parent = start
    for _ in range(3):
        if str(parent) in protected or parent == parent.parent:
            break
        try:
            parent.rmdir()
        except OSError:
            break
        removed.append(str(parent))
        parent = parent.parent
    return removed


def _write_manifest(ledger_dir: Path, report: dict, now: datetime) -> Path:
    manifest_dir = ledger_dir / "gc-manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_dir / f"gc-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


def _managed_roots(workspace: Path, extra: list[str]) -> list[Path]:
    return [
        workspace,
        Path.home() / ".opc" / "sessions",
        *(Path(root).expanduser().resolve() for root in extra),
    ]


def _assemble_report(
    workspace: Path,
    mode: str,
    now: datetime,
    compact_threshold: int,
    session_archive_days: int,
    ledger_dir: Path,
    registry: Path,
    entries: list[dict],
    torn: int,
    raw: list[str],
) -> tuple[dict, dict]:
    compaction = plan_compaction(raw, now, compact_threshold)
    ledger_path_set = {rec["path"] for rec in entries if isinstance(rec.get("path"), str)}
    report = {
        "mode": mode,
        "workspace": str(workspace),
        "started_at": iso(now),
        "ledger": {
            "path": str(registry),
            "entries": len(entries),
            "torn_lines": torn,
            "exists": registry.is_file(),
        },
        "deletions": {},
        "compaction": {k: v for k, v in compaction.items() if k != "kept_raw"},
        "tripwire": tripwire_report(
            workspace,
            ledger_dir,
            ledger_path_set,
            ledger_dir / "tripwire-baseline.json",
            mode,
            now,
        ),
        "sessions": session_inventory(now, session_archive_days),
        "static": static_inventory(workspace),
        "lifetime_table": LIFETIME_TABLE,
    }
    return report, compaction


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
    managed_roots = _managed_roots(workspace, extra_managed_roots)
    entries, torn, raw = load_ledger(registry)
    delete, skipped, missing = plan_deletions(entries, managed_roots, ledger_dir, now)
    report, compaction = _assemble_report(
        workspace,
        mode,
        now,
        compact_threshold,
        session_archive_days,
        ledger_dir,
        registry,
        entries,
        torn,
        raw,
    )
    report["deletions"] = {
        "candidates": delete,
        "skipped": skipped,
        "already_missing": missing,
    }
    if mode != "execute":
        return report
    return _execute_mode(report, compaction, delete, managed_roots, ledger_dir, registry, now)


def _execute_mode(
    report: dict,
    compaction: dict,
    delete: list[dict],
    managed_roots: list[Path],
    ledger_dir: Path,
    registry: Path,
    now: datetime,
) -> dict:
    removed, failed, empty_dirs = _execute_deletions(delete, managed_roots)
    report["deletions"]["removed"] = removed
    report["deletions"]["failed"] = failed
    report["deletions"]["removed_empty_dirs"] = empty_dirs
    report["bytes_reclaimed"] = sum(item["bytes"] or 0 for item in removed)
    if compaction["would_compact"]:
        kept_raw = compaction["kept_raw"]
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(("\n".join(kept_raw) + "\n") if kept_raw else "", encoding="utf-8")
        report["compaction"]["executed"] = True
    report["manifest_path"] = str(_write_manifest(ledger_dir, report, now))
    return report


def print_summary(report: dict) -> None:
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
