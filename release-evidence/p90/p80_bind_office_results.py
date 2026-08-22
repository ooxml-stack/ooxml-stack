"""Bind P80 semantic-promotion rows to fresh Office replay results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonl_artifacts import read_jsonl, write_jsonl

OUT = Path(__file__).resolve().parent
ROWS = OUT / "p80-semantic-promotion-rows.jsonl"
OFFICE = OUT / "p80-semantic-promotion-office.json"


def main() -> int:
    rows = read_jsonl(ROWS)
    office = json.loads(OFFICE.read_text(encoding="utf-8"))
    bound = bind_rows(rows, office)
    write_jsonl(ROWS, bound)
    _write_json(OUT / "p80-semantic-promotion-summary.json", summary(bound, office))
    return 0 if office.get("summary", {}).get("gate_pass") is True else 1


def bind_rows(rows: list[dict[str, Any]], office: dict[str, Any]) -> list[dict[str, Any]]:
    results = {_path_key(row.get("file", "")): row for row in office.get("results", [])}
    return [_bind_one(row, results) for row in rows]


def _bind_one(row: dict[str, Any], results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    output = _path_key(row.get("output_file", ""))
    result = results.get(output)
    if not result or row.get("semantic_edit_pass") is not True:
        return row
    bound = dict(row)
    bound["native_office_result"] = result.get("status")
    bound["office_result_id"] = output
    bound["pass"] = result.get("status") == "pass"
    return bound


def summary(rows: list[dict[str, Any]], office: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "p90-p80-semantic-promotion-v1",
        "gate_pass": bool(rows) and all(row.get("pass") for row in rows),
        "row_count": len(rows),
        "row_pass_count": sum(row.get("pass") is True for row in rows),
        "semantic_edit_pass_count": sum(row.get("semantic_edit_pass") is True for row in rows),
        "native_office_pass_count": sum(row.get("native_office_result") == "pass" for row in rows),
        "pending_native_office_count": sum(row.get("native_office_result") == "not-run" for row in rows),
        "office_gate_pass": office.get("summary", {}).get("gate_pass") is True,
    }


def _path_key(path: str) -> str:
    parts = Path(path).parts
    if "ooxml-stack" in parts:
        return str(Path(*parts[parts.index("ooxml-stack") :]))
    return path


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
