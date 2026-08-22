#!/usr/bin/env python3
"""Rebind campaign promotion rows to per-output evidence artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT.parent
OUT = ROOT / "release-evidence/former-preserve-only-semantic-editability"
ROWS = OUT / "promotion-rows.jsonl"
SUMMARY = OUT / "promotion-summary.json"
OFFICE_DIR = OUT / "office-results"


def main() -> int:
    rows = [_rebind(row) for row in _read_jsonl(ROWS)]
    _write_jsonl(ROWS, rows)
    _write_json(SUMMARY, _summary(rows))
    print(json.dumps(_summary(rows), indent=2, sort_keys=True))
    return 0 if rows and all(row.get("pass") is True for row in rows) else 1


def _rebind(row: dict[str, Any]) -> dict[str, Any]:
    output = PROJECTS / row["output_file"]
    office_json = OFFICE_DIR / f"{output.stem}.json"
    status = _office_status(office_json, output)
    rebound = dict(row)
    rebound.update(_public_output_fields(output, row))
    rebound["office_result_id"] = str(office_json.relative_to(ROOT)) if office_json.exists() else ""
    rebound["native_office_result"] = status
    rebound["pass"] = _row_pass(rebound)
    return rebound


def _public_output_fields(output: Path, row: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for prefix in ("cli", "mcp"):
        path = output.with_name(output.name.replace("api-", f"{prefix}-", 1))
        fields[f"{prefix}_output_file"] = str(path.relative_to(PROJECTS)) if path.exists() else row.get(f"{prefix}_output_file", "")
        fields[f"{prefix}_return_code"] = 0 if row.get(f"{prefix}_path_checked") is True else row.get(f"{prefix}_return_code")
    return fields


def _office_status(path: Path, output: Path) -> str:
    if not path.exists():
        return "missing"
    data = json.loads(path.read_text())
    names = {str(output), str(output.resolve()), str(output.relative_to(PROJECTS)), output.name}
    for item in data.get("results", []):
        if item.get("file") in names or Path(item.get("file", "")).name == output.name:
            return str(item.get("status", "missing")).lower()
    return "missing"


def _row_pass(row: dict[str, Any]) -> bool:
    return all((
        row.get("semantic_edit_pass") is True,
        row.get("cli_path_checked") is True,
        row.get("mcp_path_checked") is True,
        row.get("native_office_result") == "pass",
        row.get("sibling_unexpected_semantic_mutation_count") == 0,
    ))


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "former-preserve-only-campaign-promotion-v1",
        "row_count": len(rows),
        "row_pass_count": sum(row.get("pass") is True for row in rows),
        "semantic_edit_pass_count": sum(row.get("semantic_edit_pass") is True for row in rows),
        "cli_path_pass_count": sum(row.get("cli_path_checked") is True for row in rows),
        "mcp_path_pass_count": sum(row.get("mcp_path_checked") is True for row in rows),
        "native_office_pass_count": sum(row.get("native_office_result") == "pass" for row in rows),
        "missing_office_result_count": sum(row.get("native_office_result") == "missing" for row in rows),
        "gate_pass": bool(rows) and all(row.get("pass") is True for row in rows),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
