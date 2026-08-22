#!/usr/bin/env python3
"""Exact replay close-error Office-only pass candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import former_preserve_only_promote_chunked as chunked
from build_close_error_rerun_report import OUT_JSON
from semantic_editability_unlock_common import EVIDENCE

CHECKPOINT = EVIDENCE / "chunk-promotion-checkpoint.json"
STAGED = EVIDENCE / "staged-rows"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    promoted = set() if args.include_existing else _promoted_chunks(CHECKPOINT)
    handled = set() if args.include_existing else _handled_hashes(CHECKPOINT)
    records = _selected_records(_read_json(OUT_JSON).get("records", []), args, promoted)
    hydrated = _hydrated_row_ids()
    chunks, row_sets = _build_replay_inputs(records, handled, hydrated)
    if args.dry_run:
        print(json.dumps({"selected": chunks, "row_sets": row_sets}, indent=2, sort_keys=True))
        return 0
    if not chunks:
        print(json.dumps({"processed": 0, "records": []}, indent=2))
        return 1
    with tempfile.TemporaryDirectory(prefix="close-error-exact-") as tmp:
        tmp_path = Path(tmp)
        plan = tmp_path / "chunk-plan-summary.json"
        row_ids = tmp_path / "chunk-row-ids.jsonl"
        _write_plan(plan, chunks, row_ids)
        _write_row_ids(row_ids, row_sets)
        original_row_ids = chunked.ROW_IDS
        chunked.ROW_IDS = row_ids
        try:
            return chunked.main(
                [
                    "--execute",
                    "--run-office",
                    "--retry-failed",
                    "--max-chunks",
                    "0",
                    "--label-prefix",
                    args.label_prefix,
                    "--plan",
                    str(plan),
                    "--checkpoint",
                    str(CHECKPOINT),
                ]
            )
        finally:
            chunked.ROW_IDS = original_row_ids


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-label", action="append", default=[])
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--label-prefix", default="close-rerun-recovery")
    parser.add_argument("--include-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _selected_records(records: list[dict[str, Any]], args: argparse.Namespace, promoted: set[str]) -> list[dict[str, Any]]:
    selected = [row for row in records if _is_exact_replay_candidate(row, args.source_label, promoted)]
    return selected[-args.limit :] if args.limit else selected


def _is_exact_replay_candidate(row: dict[str, Any], labels: list[str], promoted: set[str]) -> bool:
    if labels and row.get("source_label") not in set(labels):
        return False
    if row.get("source_chunk_id") in promoted:
        return False
    return row.get("classification") == "automation_transient" and row.get("promotion_eligible_after_rerun") is True


def _build_replay_inputs(records: list[dict[str, Any]], handled: set[str] | None = None, hydrated: set[str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    handled = handled or set()
    hydrated = hydrated or set()
    chunks, row_sets = [], []
    for index, record in enumerate(records, start=1):
        staged = STAGED / f"{record['source_chunk_id']}.jsonl"
        rows = _read_jsonl(staged)
        row_ids = [row["row_id"] for row in rows]
        if _row_ids_hash(row_ids) in handled:
            continue
        if hydrated and any(row_id not in hydrated for row_id in row_ids):
            continue
        chunk = _chunk(record, row_ids, index)
        chunks.append(chunk)
        row_sets.append({"chunk_id": chunk["chunk_id"], "row_ids": row_ids})
    return chunks, row_sets


def _chunk(record: dict[str, Any], row_ids: list[str], index: int) -> dict[str, Any]:
    return {
        "chunk_id": record["source_chunk_id"],
        "chunk_index": index,
        "family": record.get("family", ""),
        "operation_ids": record.get("operation_ids", []),
        "package_id": record["package_id"],
        "planned_row_count": len(row_ids),
        "row_ids_hash": _row_ids_hash(row_ids),
    }


def _write_plan(path: Path, chunks: list[dict[str, Any]], row_ids: Path) -> None:
    payload = {
        "schema_version": "close-error-exact-replay-plan-v1",
        "chunk_count": len(chunks),
        "chunks": chunks,
        "planned_chunk_count": len(chunks),
        "row_ids_artifact": str(row_ids),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_row_ids(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _row_ids_hash(row_ids: list[str]) -> str:
    return hashlib.sha256(("\n".join(row_ids) + "\n").encode()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _promoted_chunks(path: Path) -> set[str]:
    records = _read_json(path).get("records", [])
    return {row.get("chunk_id", "") for row in records if row.get("status") == "promoted"}


def _handled_hashes(path: Path) -> set[str]:
    records = _read_json(path).get("records", [])
    return {
        row.get("row_ids_hash", "")
        for row in records
        if str(row.get("label", "")).startswith("close-rerun-recovery-") and row.get("status") in {"promoted", "office_boundary"}
    }


def _hydrated_row_ids() -> set[str]:
    return {row["row_id"] for row in chunked.promote._read_jsonl(chunked.HYDRATED)}


if __name__ == "__main__":
    raise SystemExit(main())
