"""P83 scalable object-level text semantic editing batch runner."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ooxml-operation-engine" / "src"))
sys.path.insert(0, str(ROOT / "ooxml-stack" / "scripts"))

from evidence_artifact_store import store_artifact  # noqa: E402
from ooxml_operation_engine.jsonrpc_server import JsonRpcServer  # noqa: E402

OUT = Path(__file__).resolve().parent
DENOMINATOR = OUT.parent / "p82" / "sh-semantic-denominator.jsonl"
GROUPS = [("docx", "text_container"), ("docx", "table_cell_text"), ("pptx", "text_container"), ("pptx", "table_cell_text")]
ARTIFACTS = ROOT / "ooxml-stack" / "release-evidence" / "artifact-blobs"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = _select_rows(args.rows_per_group, args.max_bytes)
    shutil.rmtree(OUT / "batch-outputs", ignore_errors=True)
    evidence, packages = _run_packages(rows)
    summary = _summary(evidence, packages, args.rows_per_group, args.max_bytes)
    _write_json("text-semantic-batch-rows.json", {"rows": evidence})
    _write_json("text-semantic-batch-summary.json", summary)
    return 0 if summary["gate_pass"] else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows-per-group", type=int, default=5)
    parser.add_argument("--max-bytes", type=int, default=2_000_000)
    return parser.parse_args(argv)


def _select_rows(rows_per_group: int, max_bytes: int) -> list[dict[str, Any]]:
    buckets = {group: [] for group in GROUPS}
    seen = set()
    with DENOMINATOR.open() as stream:
        for line in stream:
            row = json.loads(line)
            group = (row.get("format"), row.get("family"))
            if not _row_selectable(row, group, buckets, rows_per_group, max_bytes, seen):
                continue
            buckets[group].append(row)
            seen.add(row["row_id"])
            if all(len(items) >= rows_per_group for items in buckets.values()):
                break
    _raise_if_missing(buckets, rows_per_group)
    return [row for group in GROUPS for row in buckets[group]]


def _row_selectable(row, group, buckets, rows_per_group, max_bytes, seen) -> bool:
    if group not in buckets or len(buckets[group]) >= rows_per_group:
        return False
    if row.get("row_id") in seen or row.get("status") != "semantic-ready":
        return False
    if not row.get("text_preview") or _input_size(row) > max_bytes:
        return False
    return True


def _raise_if_missing(buckets: dict[tuple[str, str], list[dict[str, Any]]], rows_per_group: int) -> None:
    missing = {f"{fmt}:{family}": rows_per_group - len(rows) for (fmt, family), rows in buckets.items() if len(rows) < rows_per_group}
    if missing:
        raise RuntimeError(f"P83 batch row selection missing groups: {missing}")


def _run_packages(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence = []
    packages = []
    for package_rows in _rows_by_input(rows).values():
        output = _copy_package(package_rows[0])
        package_evidence = _run_one_package(output, package_rows)
        evidence.extend(package_evidence)
        packages.append({"input_file": package_rows[0]["input_file"], "output_file": _rel(output), "artifact": store_artifact(output, ARTIFACTS, ROOT), "row_count": len(package_evidence), "pass": all(row["pass"] for row in package_evidence)})
    return evidence, packages


def _run_one_package(output: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    server = JsonRpcServer()
    server.handle("ooxml_open", {"path": str(output)})
    try:
        return [_run_row(server, output, row, i) for i, row in enumerate(rows)]
    finally:
        try:
            server.handle("ooxml_save", {})
            server.handle("ooxml_close", {})
        except Exception:
            server.cleanup()


def _run_row(server: JsonRpcServer, output: Path, row: dict[str, Any], index: int) -> dict[str, Any]:
    handle = _current_handle(server, row)
    after_text = _after_text(row, index)
    result = server.handle("ooxml_apply", _payload(row, handle, after_text))
    diff = result.get("semantic_diff", {})
    return {
        "row_id": row["row_id"],
        "format": row["format"],
        "input_file": row["input_file"],
        "output_file": _rel(output),
        "family": row["family"],
        "stable_id": row["stable_id"],
        "selector": row["selector"],
        "operation_id": row["operation_id"],
        "semantic_model_id": "text.container.v1" if row["family"] == "text_container" else "table.cell.text.v1",
        "before_text": handle["text"],
        "after_text": after_text,
        "target_semantic_hit": diff.get("target_changed") is True,
        "sibling_unchanged": diff.get("sibling_safety_passed") is True,
        "sibling_checked_count": diff.get("sibling_checked_count", 0),
        "validation_pass": result.get("provenance", {}).get("validation", {}).get("passed") is True,
        "pass": _row_pass(result),
    }


def _current_handle(server: JsonRpcServer, row: dict[str, Any]) -> dict[str, Any]:
    handles = server.handle("ooxml_semantic_handles", {})["handles"]
    for handle in handles:
        if handle["stable_id"] == row["stable_id"] and handle["target"] == row["selector"]:
            return handle
    raise RuntimeError(f"Handle not found for {row['row_id']}")


def _payload(row: dict[str, Any], handle: dict[str, Any], text: str) -> dict[str, Any]:
    return {"stable_id": handle["stable_id"], "snapshot_id": handle["snapshot_id"], "operation_id": row["operation_id"], "params": {"text": text}}


def _row_pass(result: dict[str, Any]) -> bool:
    diff = result.get("semantic_diff", {})
    validation = result.get("provenance", {}).get("validation", {})
    return diff.get("target_changed") is True and diff.get("sibling_safety_passed") is True and validation.get("passed") is True


def _summary(rows: list[dict[str, Any]], packages: list[dict[str, Any]], rows_per_group: int, max_bytes: int) -> dict[str, Any]:
    return {
        "claim": "P83 expanded text semantic active editing batch evidence; still not full text/table denominator completion.",
        "gate_pass": all(row["pass"] for row in rows) and all(package["pass"] for package in packages),
        "full_denominator_pass": False,
        "rows_per_group": rows_per_group,
        "max_input_bytes": max_bytes,
        "object_row_count": len(rows),
        "object_row_pass_count": sum(1 for row in rows if row["pass"]),
        "package_output_count": len(packages),
        "target_semantic_miss_count": sum(1 for row in rows if not row["target_semantic_hit"]),
        "sibling_unexpected_semantic_mutation_count": sum(1 for row in rows if not row["sibling_unchanged"]),
        "validation_failure_count": sum(1 for row in rows if not row["validation_pass"]),
        "groups": _group_counts(rows),
        "packages": packages,
    }


def _rows_by_input(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["input_file"]].append(row)
    return grouped


def _group_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = f"{row['format']}:{row['family']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _copy_package(row: dict[str, Any]) -> Path:
    src = ROOT / "ooxml-native-corpus" / row["input_file"]
    dst_dir = OUT / "batch-outputs"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"batch-{row['package_id']}{src.suffix}"
    shutil.copy2(src, dst)
    return dst


def _input_size(row: dict[str, Any]) -> int:
    return (ROOT / "ooxml-native-corpus" / row["input_file"]).stat().st_size


def _after_text(row: dict[str, Any], index: int) -> str:
    return f"P83 batch semantic edit {index} {row['format']} {row['family']}"


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _write_json(name: str, data: dict[str, Any]) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
