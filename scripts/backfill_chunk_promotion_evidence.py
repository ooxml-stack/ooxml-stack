#!/usr/bin/env python3
"""Backfill chunk-level fields onto promoted chunk evidence rows."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

import former_preserve_only_promote_hydrated as promote
from former_preserve_only_chunk_evidence import enrich_rows, normalize_checkpoint

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release-evidence/former-preserve-only-semantic-editability"
PROJECTS = ROOT.parent
CHECKPOINT = OUT / "chunk-promotion-checkpoint.json"
STAGED = OUT / "staged-rows"


def main() -> int:
    checkpoint = normalize_checkpoint(_read_json(CHECKPOINT))
    records = _promoted_records(checkpoint)
    rows = [_backfill_row(row, records) for row in promote._read_jsonl(promote.ROWS)]
    promote._write_jsonl(promote.ROWS, rows)
    for path in STAGED.glob("*.jsonl"):
        staged = [_backfill_row(row, records) for row in promote._read_jsonl(path)]
        promote._write_jsonl(path, staged)
    _write_checkpoint(checkpoint, rows)
    promote._write_json(promote.SUMMARY, promote._summary(rows, 0, "chunk-backfill"))
    print(json.dumps(_summary(rows), indent=2, sort_keys=True))
    return 0


def _backfill_row(row: dict[str, Any], records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    record = _record_for_row(row, records)
    if not record:
        return row
    chunk = {
        "chunk_id": record["chunk_id"],
        "package_id": record.get("package_id"),
        "family": record.get("family"),
    }
    return enrich_rows([row], chunk, record["label"], record.get("office", {}))[0]


def _record_for_row(row: dict[str, Any], records: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for label, record in records.items():
        if _row_has_label(row, label):
            return record
    return None


def _promoted_records(checkpoint: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["label"]: row for row in checkpoint.get("records", []) if row.get("status") == "promoted"}


def _write_checkpoint(checkpoint: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    chunk_rows = _chunk_rows(rows)
    for record in checkpoint.get("records", []):
        group = chunk_rows.get(record.get("chunk_id"), [])
        _fill_record(record, group, checkpoint.get("plan_hash", ""))
    CHECKPOINT.write_text(json.dumps(normalize_checkpoint(checkpoint), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fill_record(record: dict[str, Any], rows: list[dict[str, Any]], plan_hash: str) -> None:
    label = str(record.get("label", ""))
    record.setdefault("plan_hash", plan_hash)
    record.setdefault("row_ids_hash", _row_ids_hash(rows))
    record.setdefault("promoted_row_count", len(rows) if record.get("status") == "promoted" else 0)
    record.setdefault("office_result_file", record.get("office", {}).get("office_json", ""))
    record.setdefault("public_path_file", f"release-evidence/former-preserve-only-semantic-editability/public-paths/cli-{label}.jsonl")
    record.setdefault("hard_audit_result", record.get("audit", {}))
    record.setdefault("input_package_hash", _input_hash(rows))
    record.setdefault("output_package_hash", _output_hash(rows))
    record.setdefault("stage_timings", {"legacy_stage_breakdown_unavailable": True, "total": record.get("duration_s", 0)})


def _chunk_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("chunk_id"):
            grouped.setdefault(row["chunk_id"], []).append(row)
    return grouped


def _row_has_label(row: dict[str, Any], label: str) -> bool:
    tokens = (f"api-{label}-", f"cli-{label}-", f"mcp-{label}-", f"cli-{label}.jsonl")
    fields = ("office_result_id", "output_file", "cli_output_file", "mcp_output_file")
    return any(token in str(row.get(field, "")) for field in fields for token in tokens)


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    chunk_rows = [row for row in rows if row.get("chunk_id")]
    return {
        "row_count": len(rows),
        "chunk_row_count": len(chunk_rows),
        "chunk_rows_with_required_aliases": sum(_has_required_aliases(row) for row in chunk_rows),
    }


def _row_ids_hash(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    return hashlib.sha256(("\n".join(row["row_id"] for row in rows) + "\n").encode()).hexdigest()


def _input_hash(rows: list[dict[str, Any]]) -> str:
    return _sha256(promote.CORPUS / rows[0]["input_file"]) if rows else ""


def _output_hash(rows: list[dict[str, Any]]) -> str:
    return _sha256(_artifact_path(rows[0].get("output_file", ""))) if rows else ""


def _artifact_path(value: str) -> Path:
    path = Path(value)
    return PROJECTS / path if not path.is_absolute() else path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _has_required_aliases(row: dict[str, Any]) -> bool:
    keys = ("chunk_id", "chunk_label", "requested_semantic_value", "native_office_status", "native_office_result_file")
    return all(key in row for key in keys)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


if __name__ == "__main__":
    raise SystemExit(main())
