#!/usr/bin/env python3
"""Build exact-row chunk plans for semantic editability promotion."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import former_preserve_only_promote_hydrated as promote
from former_preserve_only_promoted_index import promoted_index
from semantic_editability_chunk_plan_report import build_summary, markdown
from semantic_editability_failed_rows import failed_source_ids
from semantic_editability_row_filter import eligible_rows
from semantic_editability_skip_packages import chunk_plan_skip_packages

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT.parent
CORPUS = PROJECTS / "ooxml-native-corpus"
OUT = ROOT / "release-evidence/former-preserve-only-semantic-editability"
HYDRATED = OUT / "operation-hydration-ledger.jsonl"
ROWS = OUT / "promotion-rows.jsonl"
REMAINING = OUT / "remaining-bucket-summary.json"
CHECKPOINT = OUT / "chunk-promotion-checkpoint.json"
STAGED = OUT / "staged-rows"
SUMMARY = OUT / "chunk-plan-summary.json"
ROW_IDS = OUT / "chunk-row-ids.jsonl"
DASHBOARD = OUT / "chunk-plan-dashboard.md"

def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    remaining = _read_json(REMAINING)
    promoted_sources, promoted_targets = promoted_index(ROWS)
    plan, row_sets = build_plan(
        _read_jsonl(HYDRATED),
        remaining,
        promoted_sources,
        promoted_targets,
        failed_sources=failed_source_ids(CHECKPOINT, STAGED),
        chunk_size=args.chunk_size,
        package_limit=args.package_limit,
        package_id=args.package_id,
        family=args.family,
        fmt=args.format,
        operation_id=args.operation_id,
        qname=args.qname,
        max_package_mb=args.max_package_mb,
        include_boundary=args.include_boundary,
        include_replay_timeout_canary=args.include_replay_timeout_canary,
        runner_filter=not args.no_runner_filter,
    )
    _write_json(SUMMARY, plan)
    _write_jsonl(ROW_IDS, row_sets)
    DASHBOARD.write_text(markdown(plan), encoding="utf-8")
    print(json.dumps({"summary": str(SUMMARY), "row_ids": str(ROW_IDS), "dashboard": str(DASHBOARD)}, indent=2))
    return 0

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-size", type=int, default=25)
    parser.add_argument("--package-limit", type=int, default=1)
    parser.add_argument("--max-packages", type=int)
    parser.add_argument("--package-id", default="")
    parser.add_argument("--family", default="")
    parser.add_argument("--format", default="")
    parser.add_argument("--operation-id", default="")
    parser.add_argument("--qname", default="")
    parser.add_argument("--max-package-mb", type=float, default=0.0)
    parser.add_argument("--include-boundary", action="store_true")
    parser.add_argument("--include-replay-timeout-canary", action="store_true")
    parser.add_argument("--no-runner-filter", action="store_true")
    args = parser.parse_args(argv)
    if args.include_replay_timeout_canary and not (args.package_id and args.family and args.operation_id):
        parser.error("--include-replay-timeout-canary requires --package-id, --family, and --operation-id")
    if args.max_packages is not None:
        args.package_limit = args.max_packages
    return args
def build_plan(
    hydrated: list[dict[str, Any]],
    remaining: dict[str, Any],
    promoted_sources: set[str],
    promoted_targets: set[tuple[str, str, str, str]],
    *,
    failed_sources: set[str] | None = None,
    chunk_size: int,
    package_limit: int = 0,
    package_id: str = "",
    family: str = "",
    fmt: str = "",
    operation_id: str = "",
    qname: str = "",
    max_package_mb: float = 0.0,
    include_boundary: bool = False,
    include_replay_timeout_canary: bool = False,
    runner_filter: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    canary_package = package_id if include_replay_timeout_canary else ""
    canary_family = family if include_replay_timeout_canary else ""
    canary_operation = operation_id if include_replay_timeout_canary else ""
    package_skips = chunk_plan_skip_packages(remaining, include_boundary, canary_package, canary_family, canary_operation)
    order = _candidate_order(remaining)
    failed_sources = failed_sources or set()
    rows, skipped = eligible_rows(
        hydrated,
        promoted_sources,
        promoted_targets,
        failed_sources,
        package_skips,
        _filters(package_id, family, fmt, operation_id, qname, max_package_mb),
    )
    rows = _ordered_rows(rows, order, 0)
    if runner_filter:
        rows, runner_skipped = _runner_plannable_rows(rows)
        skipped.update(runner_skipped)
    rows = _ordered_rows(rows, order, package_limit)
    chunks, row_sets = _chunks(rows, chunk_size)
    filters = dict(package_id=package_id, family=family, format=fmt, operation_id=operation_id, qname=qname)
    filters["include_replay_timeout_canary"] = include_replay_timeout_canary
    summary = _summary(chunks, row_sets, skipped, chunk_size, package_limit, include_boundary, remaining, filters)
    return summary, row_sets

def _summary(
    chunks: list[dict[str, Any]],
    row_sets: list[dict[str, Any]],
    skipped: Counter[str],
    chunk_size: int,
    package_limit: int,
    include_boundary: bool,
    remaining: dict[str, Any],
    plan_filters: dict[str, Any],
) -> dict[str, Any]:
    return build_summary(
        chunks,
        row_sets,
        skipped,
        chunk_size=chunk_size,
        package_limit=package_limit,
        include_boundary=include_boundary,
        remaining=remaining,
        remaining_path=REMAINING,
        row_ids_path=ROW_IDS,
        root=ROOT,
        plan_filters=plan_filters,
    )
def _ordered_rows(rows: list[dict[str, Any]], order: dict[tuple[str, str], int], package_limit: int) -> list[dict[str, Any]]:
    rows = sorted(rows, key=lambda row: _sort_key(row, order))
    if not package_limit:
        return rows
    allowed = _first_packages(rows, package_limit)
    return [row for row in rows if row.get("package_id") in allowed]

def _sort_key(row: dict[str, Any], order: dict[tuple[str, str], int]) -> tuple[int, str, str, str, str]:
    package = str(row.get("package_id", ""))
    family = str(row.get("family", ""))
    rank = order.get((package, family), 999_999)
    return (rank, package, family, str(row.get("part_name", "")), str(row.get("row_id", "")))

def _first_packages(rows: list[dict[str, Any]], limit: int) -> set[str]:
    packages: list[str] = []
    for row in rows:
        package = str(row.get("package_id", ""))
        if package not in packages:
            packages.append(package)
        if len(packages) >= limit:
            break
    return set(packages)

def _filters(package_id: str, family: str, fmt: str, operation_id: str, qname: str, max_package_mb: float) -> dict[str, Any]:
    return {
        "family": family,
        "fmt": fmt,
        "max_package_mb": max_package_mb,
        "operation_id": operation_id,
        "package_id": package_id,
        "package_mb_fn": _package_mb,
        "qname": qname,
    }

def _chunks(rows: list[dict[str, Any]], chunk_size: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    chunks, row_sets = [], []
    grouped = _group_rows(rows)
    for key, bucket in grouped.items():
        for index in range(0, len(bucket), chunk_size):
            items = bucket[index : index + chunk_size]
            chunk = _chunk_row(key, items, index // chunk_size, _chunk_count(len(bucket), chunk_size))
            chunks.append(chunk)
            row_sets.append({"chunk_id": chunk["chunk_id"], "row_ids": [row["row_id"] for row in items]})
    return chunks, row_sets

def _runner_plannable_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    selected, skipped = [], Counter()
    for key, bucket in _group_rows(rows).items():
        opts = SimpleNamespace(package_id=key[0], requested_value="", max_rows=len(bucket), skipped_policy_rows=0)
        try:
            plans = promote._plans(bucket, opts)
        except Exception:  # noqa: BLE001
            skipped["runner_plan_error"] += len(bucket)
            continue
        selected.extend(item["row"] for item in plans)
        skipped["runner_policy_or_overlap"] += len(bucket) - len(plans)
        skipped["runner_schema_policy"] += int(getattr(opts, "skipped_policy_rows", 0))
    return selected, skipped

def _group_rows(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("package_id", "")), str(row.get("format", "")), str(row.get("family", "")))].append(row)
    return dict(grouped)

def _chunk_row(key: tuple[str, str, str], rows: list[dict[str, Any]], index: int, count: int) -> dict[str, Any]:
    package, fmt, family = key
    row_ids = [row["row_id"] for row in rows]
    row_hash = _row_ids_hash(row_ids)
    return {
        "chunk_id": f"chunk-{_slug(package)}-{_slug(family)}-{index + 1:04d}-{row_hash[:10]}",
        "package_id": package,
        "format": fmt,
        "family": family,
        "chunk_index": index + 1,
        "chunk_count": count,
        "planned_row_count": len(rows),
        "first_row_id": row_ids[0],
        "last_row_id": row_ids[-1],
        "row_ids_hash": row_hash,
        "row_ids_path": str(ROW_IDS.relative_to(ROOT)),
        "operation_ids": sorted({str(row.get("operation_id", "")) for row in rows}),
        "qnames_top10": dict(Counter(str(row.get("qname", "")) for row in rows).most_common(10)),
        "estimated_package_mb": _package_mb(str(rows[0].get("input_file", ""))),
        "estimated_risk": _risk(rows),
        "recommended_action": "chunked_promote",
    }

def _candidate_order(remaining: dict[str, Any]) -> dict[tuple[str, str], int]:
    rows = remaining.get("candidate_packages", [])
    return {(str(row.get("package_id", "")), str(row.get("family", ""))): index for index, row in enumerate(rows)}

def _chunk_count(total: int, chunk_size: int) -> int:
    return (total + chunk_size - 1) // chunk_size


def _row_ids_hash(row_ids: list[str]) -> str:
    return hashlib.sha256(("\n".join(row_ids) + "\n").encode()).hexdigest()


def _risk(rows: list[dict[str, Any]]) -> str:
    size = _package_mb(str(rows[0].get("input_file", ""))) or 0
    if size > 25 or len(rows) > 50:
        return "medium"
    return "low"


def _package_mb(input_file: str) -> float | None:
    path = CORPUS / input_file
    return round(path.stat().st_size / 1024 / 1024, 3) if path.exists() else None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:48] or "unknown"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
