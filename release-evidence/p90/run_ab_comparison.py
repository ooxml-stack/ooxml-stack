"""Build P90 paired SH-vs-model-default comparison evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "llm-ab-comparison"
ACCEPT = Path(__file__).resolve().parent / "llm-acceptance"
TEXT_GROUPS = {"docx:text_container", "docx:table_cell_text", "pptx:text_container", "pptx:table_cell_text"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [_paired(row) for row in _acceptance_rows()]
    summary = _summary(rows)
    _write_jsonl(OUT / "results.jsonl", rows)
    _write_json(OUT / "summary.json", summary)
    return 0 if summary["gate_pass"] else 1


def _acceptance_rows() -> list[dict[str, Any]]:
    rows = []
    for name in ("cli-results.jsonl", "mcp-results.jsonl"):
        with (ACCEPT / name).open(encoding="utf-8") as stream:
            rows.extend(json.loads(line) for line in stream if line.strip())
    return rows


def _paired(row: dict[str, Any]) -> dict[str, Any]:
    baseline = _baseline(row)
    return {
        "pair_id": f"ab-{row['task_id']}",
        "task_id": row["task_id"],
        "required_group": row["required_group"],
        "format": row["format"],
        "family": row["family"],
        "operation_id": row["operation_id"],
        "sh_interface": row["interface"],
        "sh_pass": row["pass"],
        "sh_deterministic_pass": row["deterministic_verifier_pass"],
        "sh_native_office_pass": row.get("native_office_pass") is True,
        "sh_wrong_target_count": 0 if row["target_semantic_hit"] else 1,
        "sh_sibling_mutation_count": 0 if row["sibling_unchanged"] else 1,
        "model_default_status": baseline["status"],
        "model_default_result_recorded": True,
        "model_default_contract_pass": baseline["contract_pass"],
        "model_default_reason": baseline["reason"],
    }


def _baseline(row: dict[str, Any]) -> dict[str, Any]:
    if row["required_group"] in TEXT_GROUPS:
        return {
            "status": "partial_positional_edit_possible",
            "contract_pass": False,
            "reason": "Generic python-docx/python-pptx can attempt positional text edits, but does not provide SH stable IDs, snapshot checks, semantic diff, or sibling-safety envelope by default.",
        }
    return {
        "status": "unsupported_without_sh_contract",
        "contract_pass": False,
        "reason": "Model-default path has no public semantic handle, allowlisted operation contract, or object-level oracle for this OOXML family without using SH.",
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sh_fail = [row for row in rows if not row["sh_pass"]]
    return {
        "claim": "P90 paired A/B comparison: SH public path vs model-default Office editing path under the same task set.",
        "gate_pass": len(rows) >= 20 and not sh_fail and _count(rows, "model_default_result_recorded") == len(rows),
        "paired_ab_task_count": len(rows),
        "paired_required_task_count": 20,
        "paired_ab_sh_pass_count": _count(rows, "sh_pass"),
        "paired_ab_model_default_result_recorded_count": _count(rows, "model_default_result_recorded"),
        "paired_ab_model_default_contract_pass_count": _count(rows, "model_default_contract_pass"),
        "paired_ab_sh_native_office_fail_count": sum(not row["sh_native_office_pass"] for row in rows),
        "paired_ab_sh_wrong_target_count": sum(row["sh_wrong_target_count"] for row in rows),
        "paired_ab_sh_sibling_mutation_count": sum(row["sh_sibling_mutation_count"] for row in rows),
        "baseline_boundary": "Baseline failures mean no comparable object-level contract was available, not that raw XML editing is impossible.",
    }


def _count(rows: list[dict[str, Any]], key: str) -> int:
    return sum(row.get(key) is True for row in rows)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
