"""Row-level semantic promotion failures to exclude from safe plans."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FAILED_ROW_STATUSES = {"cli_failed", "hard_audit_failed", "mcp_failed", "public_api_failed"}


def failed_source_ids(checkpoint_path: Path, staged_dir: Path) -> set[str]:
    checkpoint = _read_json(checkpoint_path)
    sources: set[str] = set()
    for record in checkpoint.get("records", []):
        if record.get("status") not in FAILED_ROW_STATUSES:
            continue
        sources.update(_staged_sources(staged_dir / f"{record.get('chunk_id')}.jsonl"))
    return sources


def _staged_sources(path: Path) -> set[str]:
    sources: set[str] = set()
    for row in _read_jsonl(path):
        source = str(row.get("source_row_id", ""))
        if source:
            sources.add(source)
    return sources


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
