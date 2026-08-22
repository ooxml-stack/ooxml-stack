"""Audit current and historical public-repo hygiene risks."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from repo_hygiene_scan import (
    current_worktree_hits,
    history_content_hits,
    index_large_blobs,
    large_blob_summary,
    lfs_policy,
    object_rows,
    raw_release_evidence_hits,
)


def risk_buckets(report: dict[str, Any]) -> list[dict[str, Any]]:
    history = report["history"]
    large = report["history_large_blobs"]
    buckets = []
    add_bucket(buckets, "historical_local_paths", "high", history["user_path_blob_hit_count"])
    add_bucket(buckets, "historical_secret_like", "high", history["secret_like_blob_hit_count"])
    add_bucket(buckets, "historical_large_blobs", "medium", large["count_gt_10mb"])
    return [bucket for bucket in buckets if bucket["count"] > 0]


def add_bucket(buckets: list[dict[str, Any]], bucket_id: str, severity: str, count: int) -> None:
    summaries = {
        "historical_local_paths": "Old blobs contain local absolute paths.",
        "historical_secret_like": "Secret-like historical blobs require owner review.",
        "historical_large_blobs": "Large normal Git blobs make public history heavy.",
    }
    buckets.append({"id": bucket_id, "severity": severity, "count": count, "summary": summaries[bucket_id]})


def audit(root: Path, max_scan_mb: int) -> dict[str, Any]:
    rows = object_rows(root)
    max_scan_bytes = max_scan_mb * 1024 * 1024
    path_hits, secret_hits, scanned = history_content_hits(root, rows, max_scan_bytes)
    large = large_blob_summary(root, rows)
    current_paths = current_worktree_hits(root)
    current_raw = raw_release_evidence_hits(root)
    current_large = index_large_blobs(root)
    lfs = lfs_policy(root)
    report = build_report(
        rows, scanned, max_scan_mb, path_hits, secret_hits, large,
        current_paths, current_raw, current_large, lfs,
    )
    report["risk_buckets"] = risk_buckets(report)
    return report


def build_report(
    rows: list[dict[str, Any]],
    scanned: int,
    max_scan_mb: int,
    path_hits: list[dict[str, Any]],
    secret_hits: list[dict[str, Any]],
    large: dict[str, Any],
    current_paths: list[str],
    current_raw: list[str],
    current_large: list[dict[str, Any]],
    lfs: dict[str, Any],
) -> dict[str, Any]:
    current_safe = len(current_paths) == 0 and len(current_raw) == 0 and len(current_large) == 0 and lfs["lfs_status_clean"]
    history_safe = len(path_hits) == 0 and len(secret_hits) == 0 and large["count_gt_10mb"] == 0
    return {
        "schema_version": "ooxml-stack-full-history-hygiene-audit-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "current_worktree": current_summary(current_paths, current_raw, current_large, lfs),
        "history": history_summary(rows, scanned, max_scan_mb, path_hits, secret_hits, large),
        "history_user_path_blob_hits": path_hits[:50],
        "history_secret_like_blob_hits": secret_hits[:50],
        "history_large_blobs": large,
        "lfs_policy": lfs,
        "recommended_public_release_option": "fresh_public_mirror" if not history_safe else "keep_private",
        "public_safe_current_worktree": current_safe,
        "public_safe_full_history": history_safe,
    }


def history_summary(
    rows: list[dict[str, Any]],
    scanned: int,
    max_scan_mb: int,
    path_hits: list[dict[str, Any]],
    secret_hits: list[dict[str, Any]],
    large: dict[str, Any],
) -> dict[str, Any]:
    return {
        "blob_count": len(rows),
        "scanned_blob_count": scanned,
        "skipped_blob_count": len(rows) - scanned,
        "privacy_scan_max_blob_mb": max_scan_mb,
        "user_path_blob_hit_count": len(path_hits),
        "secret_like_blob_hit_count": len(secret_hits),
        "large_blob_count_gt_10mb": large["count_gt_10mb"],
        "large_blob_count_gt_50mb": large["count_gt_50mb"],
        "large_blob_count_gt_100mb": large["count_gt_100mb"],
    }


def current_summary(
    current_paths: list[str],
    current_raw: list[str],
    current_large: list[dict[str, Any]],
    lfs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "user_path_hit_count": len(current_paths),
        "user_path_hits": current_paths[:50],
        "raw_release_evidence_user_path_hit_count": len(current_raw),
        "raw_release_evidence_user_path_hits": current_raw[:50],
        "index_blob_over_10mb_count": len(current_large),
        "index_blob_over_10mb": current_large[:50],
        "lfs_status_clean": lfs["lfs_status_clean"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="artifacts/ooxml-stack-full-history-hygiene-audit.json")
    parser.add_argument("--max-scan-mb", type=int, default=25)
    parser.add_argument("--strict-history", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = audit(root, args.max_scan_mb)
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(out.relative_to(root))
    if not report["public_safe_current_worktree"]:
        return 1
    if args.strict_history and not report["public_safe_full_history"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
