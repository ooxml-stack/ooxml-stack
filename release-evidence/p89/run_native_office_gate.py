"""P89 full measured native Office compatibility gate."""

from __future__ import annotations

import argparse, hashlib, json, subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RUNNER = "ooxml-test-framework/tools/office-open-gate/office_open_gate.py"
NON_BLOCKING = {"pass", "pass_with_dialog"}
ROW_FILES = [
    ("p83-api", "release-evidence/p83/text-semantic-edit-rows.json"),
    ("p83-cli", "release-evidence/p83/text-semantic-cli-smoke.json"),
    ("p83-mcp", "release-evidence/p83/text-semantic-mcp-smoke.json"),
    ("p83-batch", "release-evidence/p83/text-semantic-batch-rows.json"),
    ("p84", "release-evidence/p84/custom-xml-semantic-rows.json"),
    ("p85", "release-evidence/p85/omml-semantic-rows.json"),
    ("p86", "release-evidence/p86/vml-semantic-rows.json"),
    ("p87", "release-evidence/p87/chart-extension-semantic-rows.json"),
    ("p88", "release-evidence/p88/structural-semantic-rows.json"),
]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source_rows = _load_source_rows()
    paths = _edited_paths(source_rows)
    raw = _run_office(paths, args.run_office)
    office_by_file = _office_by_file(raw)
    bound_rows = [_bind_row(row, office_by_file) for row in source_rows]
    summary = _summary(bound_rows, raw, paths)
    _write_jsonl(OUT / "native-office-gate.object-bound.jsonl", bound_rows)
    _write_json(OUT / "native-office-gate-summary.json", summary)
    return 0 if summary["gate_pass"] else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-office", action="store_true")
    return parser.parse_args(argv)


def _load_source_rows() -> list[dict[str, Any]]:
    rows = []
    for phase, rel in ROW_FILES:
        loaded = _rows_from_json(ROOT / "ooxml-stack" / rel)
        rows.extend(_normalize_source_row(phase, row) for row in loaded)
    return rows


def _rows_from_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    rows = data.get("rows")
    if isinstance(rows, list):
        return rows
    raise ValueError(f"No rows in {path}")


def _normalize_source_row(phase: str, row: dict[str, Any]) -> dict[str, Any]:
    return row | {"source_phase": phase, "source_row_id": row.get("row_id", "")}


def _edited_paths(rows: list[dict[str, Any]]) -> list[Path]:
    paths = []
    seen = set()
    for row in rows:
        rel = row.get("output_file", "")
        if not rel:
            raise ValueError(f"missing output_file: {row.get('row_id')}")
        path = (ROOT / rel).resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        key = str(path)
        if key not in seen:
            paths.append(path); seen.add(key)
    return paths


def _run_office(paths: list[Path], enabled: bool) -> dict[str, Any]:
    raw_path = OUT / "native-office-gate.raw.json"
    if not enabled:
        return {"summary": {"gate_pass": False, "skipped": True}, "results": []}
    cmd = [
        "uv", "run", "python", "tools/office-open-gate/office_open_gate.py",
        *[str(path) for path in paths], "--timeout-seconds", "120",
        "--dialog-wait-seconds", "8", "--path-root", str(ROOT), "-o", str(raw_path),
    ]
    subprocess.run(cmd, cwd=ROOT / "ooxml-test-framework", check=False)
    return json.loads(raw_path.read_text(encoding="utf-8"))


def _office_by_file(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapped = {}
    for index, result in enumerate(raw.get("results", [])):
        result = result | {"office_result_id": _office_result_id(index, result)}
        mapped[_rel_key(result.get("file", ""))] = result
    return mapped


def _bind_row(row: dict[str, Any], office_by_file: dict[str, dict[str, Any]]) -> dict[str, Any]:
    key = _rel_key(row["output_file"])
    office = office_by_file.get(key, {"status": "missing_office_result", "office_result_id": ""})
    semantic_hit = row.get("target_semantic_hit") is True
    sibling_ok = _sibling_ok(row)
    validation_ok = row.get("validation_pass") is True
    office_pass = office.get("status") in NON_BLOCKING
    object_pass = row.get("pass") is True and semantic_hit and sibling_ok and validation_ok
    return {
        "p89_row_id": _p89_row_id(row), "source_phase": row["source_phase"],
        "source_row_id": row["source_row_id"], "format": row.get("format", ""),
        "input_file": row.get("input_file", ""), "output_file": row.get("output_file", ""),
        "family": row.get("family", ""), "operation_id": row.get("operation_id", ""),
        "stable_id": row.get("stable_id", ""), "selector": row.get("selector", ""),
        "target_semantic_hit": semantic_hit, "sibling_unchanged": sibling_ok,
        "validation_pass": validation_ok, "object_pass": object_pass,
        "office_result_id": office.get("office_result_id", ""),
        "office_status": office.get("status", "missing_office_result"),
        "office_message": office.get("message", ""), "office_gate_pass": office_pass,
        "pass": object_pass and office_pass,
    }


def _sibling_ok(row: dict[str, Any]) -> bool:
    if "sibling_unchanged" in row:
        return row.get("sibling_unchanged") is True
    return row.get("sibling_unexpected_semantic_mutation_count", 0) == 0


def _summary(rows: list[dict[str, Any]], raw: dict[str, Any], paths: list[Path]) -> dict[str, Any]:
    raw_summary = raw.get("summary", {})
    semantic_hit_count = sum(row["target_semantic_hit"] for row in rows)
    object_pass_count = sum(row["object_pass"] for row in rows)
    office_row_count = sum(row["office_gate_pass"] for row in rows)
    return {
        "claim": "P89 object-bound native Office gate over P83-P88 edited SH outputs.",
        "gate_pass": _gate_pass(rows, raw, raw_summary, paths, semantic_hit_count, office_row_count),
        "p81_native_office_preflight_reused": _p81_preflight_pass(),
        "p89_native_office_runner": RUNNER,
        "p89_native_office_automation_method": "macos-osascript",
        "p89_headless_substitution_count": 0,
        "object_row_count": len(rows), "object_row_pass_count": object_pass_count,
        "semantic_hit_count": semantic_hit_count,
        "p89_edited_package_count": len(paths),
        "p89_completed_package_count": raw_summary.get("total", 0),
        "p89_office_pass_package_count": raw_summary.get("pass_total", 0),
        "p89_object_bound_office_row_count": office_row_count,
        "p89_unbound_package_level_pass_count": _unbound_pass_count(raw, rows),
        "p89_repair_dialog_count": raw_summary.get("repair_dialog_count", 0),
        "p89_security_dialog_count": raw_summary.get("security_dialog_count", 0),
        "p89_crash_count": raw_summary.get("office_crash_count", 0),
        "p89_timeout_count": raw_summary.get("timeout_count", 0),
        "office_status_counts": raw_summary.get("by_status", {}),
        "source_phase_counts": _counts(row["source_phase"] for row in rows),
        "operation_counts": _counts(row["operation_id"] for row in rows),
    }


def _gate_pass(rows, raw, raw_summary, paths, semantic_hit_count, office_row_count) -> bool:
    return all(row["pass"] for row in rows) and _p81_preflight_pass() and raw_summary.get("gate_pass") is True and raw_summary.get("total") == len(paths) and raw_summary.get("pass_total") == len(paths) and office_row_count == semantic_hit_count and _unbound_pass_count(raw, rows) == 0


def _p81_preflight_pass() -> bool:
    path = ROOT / "ooxml-stack/release-evidence/p81/native-office-automation-preflight.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("native_office_automation_preflight_pass") is True and data.get("automation_runner") == RUNNER


def _unbound_pass_count(raw: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    row_outputs = {_rel_key(row.get("output_file", "")) for row in rows}
    return sum(1 for item in raw.get("results", []) if item.get("status") in NON_BLOCKING and _rel_key(item.get("file", "")) not in row_outputs)


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _p89_row_id(row: dict[str, Any]) -> str:
    raw = f"{row['source_phase']}|{row.get('output_file', '')}|{row.get('row_id', '')}"
    return "p89:" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _office_result_id(index: int, result: dict[str, Any]) -> str:
    raw = f"{index}|{result.get('file', '')}|{result.get('status', '')}"
    return "office:" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _rel_key(path: str) -> str:
    if not path:
        return ""
    p = Path(path)
    if p.is_absolute():
        try:
            return str(p.resolve().relative_to(ROOT))
        except ValueError:
            return str(p)
    return str(p)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
