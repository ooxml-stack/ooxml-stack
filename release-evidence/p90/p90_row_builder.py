"""Build mandatory-schema P90 rows from proven P89 object evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonl_artifacts import read_jsonl as _read_jsonl_artifact

ROOT = Path(__file__).resolve().parents[3]
STACK = ROOT / "ooxml-stack"
SOURCE_FILES = (
    ("p83-api", "release-evidence/p83/text-semantic-edit-rows.json"),
    ("p83-cli", "release-evidence/p83/text-semantic-cli-smoke.json"),
    ("p83-mcp", "release-evidence/p83/text-semantic-mcp-smoke.json"),
    ("p83-batch", "release-evidence/p83/text-semantic-batch-rows.json"),
    ("p84", "release-evidence/p84/custom-xml-semantic-rows.json"),
    ("p85", "release-evidence/p85/omml-semantic-rows.json"),
    ("p86", "release-evidence/p86/vml-semantic-rows.json"),
    ("p87", "release-evidence/p87/chart-extension-semantic-rows.json"),
    ("p88", "release-evidence/p88/structural-semantic-rows.json"),
)
PROMOTION_ROWS = "release-evidence/p90/p80-semantic-promotion-rows.jsonl"
PROMOTION_REPLAY = "release-evidence/p90/p80-semantic-promotion-public-replay.jsonl"
P90_PUBLIC_REPLAY = "release-evidence/p90/p90-public-path-replay.jsonl"
PASS_STATUSES = {"pass"}


def build_p90_rows() -> list[dict[str, Any]]:
    source = _source_index()
    denom = _denominator_index()
    public_replay = _p90_public_replay_index()
    rows = []
    for p89 in _jsonl("release-evidence/p89/native-office-gate.object-bound.jsonl"):
        src = source[(p89["source_phase"], p89["source_row_id"])]
        base = denom.get(src["row_id"], {})
        row = _p90_row(p89, src, base)
        rows.append(_with_p90_public_replay(row, public_replay.get(row["row_id"], {})))
    rows.extend(_promotion_rows())
    return rows


def _p90_row(p89: dict[str, Any], src: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    before, after, kind = _values(src)
    return {
        "row_id": _row_id(src, base),
        "format": p89.get("format", ""),
        "input_file": p89.get("input_file", ""),
        "package_id": src.get("package_id") or base.get("package_id") or _package_id(src),
        "part_name": src.get("part_name") or base.get("part_name") or _part_name(p89),
        "stable_id": p89.get("stable_id", ""),
        "stable_id_scope": "package-local",
        "selector": p89.get("selector", ""),
        "family": p89.get("family", ""),
        "semantic_model_id": src.get("semantic_model_id", _model_id(p89)),
        "operation_id": p89.get("operation_id", ""),
        "capability_tier": "semantic-active-editable",
        "understanding_level": src.get("understanding_level", _understanding(p89)),
        "before_semantic_value": _semantic_value(before, kind, src),
        "requested_semantic_change": _requested_change(p89, after, kind),
        "after_semantic_value": _semantic_value(after, kind, src),
        "target_semantic_changed": p89.get("target_semantic_hit") is True,
        "sibling_unexpected_semantic_mutation_count": _sibling_count(p89, src),
        "package_invariant_pass": p89.get("validation_pass") is True,
        "native_office_result": p89.get("office_status", ""),
        "public_api_path": _public_api_path(src),
        "cli_path_checked": src.get("interface") == "cli",
        "mcp_path_checked": src.get("interface") == "mcp",
        "llm_acceptance_task_ids": [],
        "source_phase": p89.get("source_phase", ""),
        "source_row_id": p89.get("source_row_id", ""),
        "output_file": p89.get("output_file", ""),
        "office_result_id": p89.get("office_result_id", ""),
        "pass": p89.get("pass") is True,
    }


def _values(row: dict[str, Any]) -> tuple[str, str, str]:
    if "before_text" in row or "after_text" in row:
        return str(row.get("before_text", "")), str(row.get("after_text", "")), "text"
    return str(row.get("before_value", "")), str(row.get("after_value", "")), row.get("value_kind", "value")


def _semantic_value(value: str, kind: str, row: dict[str, Any]) -> dict[str, Any]:
    return {"value": value, "value_kind": kind, "qname": row.get("qname", "")}


def _requested_change(p89: dict[str, Any], after: str, kind: str) -> dict[str, Any]:
    return {"operation_id": p89.get("operation_id", ""), "value": after, "value_kind": kind}


def _source_index() -> dict[tuple[str, str], dict[str, Any]]:
    indexed = {}
    for phase, rel in SOURCE_FILES:
        for row in _rows_from_json(rel):
            indexed[(phase, row["row_id"])] = row
    return indexed


def _denominator_index() -> dict[str, dict[str, Any]]:
    return {row["row_id"]: row for row in _jsonl("release-evidence/p82/sh-semantic-denominator.jsonl")}


def _rows_from_json(rel: str) -> list[dict[str, Any]]:
    data = json.loads((STACK / rel).read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("rows", [])


def _jsonl(rel: str) -> list[dict[str, Any]]:
    return _read_jsonl_artifact(STACK / rel)


def _promotion_rows() -> list[dict[str, Any]]:
    path = STACK / PROMOTION_ROWS
    replay = _promotion_replay_index()
    rows = _read_jsonl_artifact(path)
    ready = [row for row in rows if row.get("pass") is True and row.get("native_office_result") in PASS_STATUSES]
    return [_with_public_replay(row, replay.get(row["row_id"], {})) for row in ready]


def _promotion_replay_index() -> dict[str, dict[str, Any]]:
    rows = _read_jsonl_artifact(STACK / PROMOTION_REPLAY)
    return {row["row_id"]: row for row in rows}


def _p90_public_replay_index() -> dict[str, dict[str, Any]]:
    rows = _read_jsonl_artifact(STACK / P90_PUBLIC_REPLAY)
    return {row["row_id"]: row for row in rows if row.get("pass") is True}


def _with_public_replay(row: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    cli = replay.get("cli_path_checked") is True
    mcp = replay.get("mcp_path_checked") is True
    return row | {
        "cli_path_checked": cli,
        "mcp_path_checked": mcp,
        "public_api_path": "ooxml-engine apply + MCP ooxml_apply" if cli and mcp else row.get("public_api_path", ""),
        "public_path_replay_row_id": replay.get("row_id", ""),
        "pass": row.get("pass") is True and cli and mcp,
    }


def _with_p90_public_replay(row: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    if replay.get("pass") is not True:
        return row
    return row | {
        "cli_path_checked": replay.get("cli_path_checked") is True,
        "mcp_path_checked": replay.get("mcp_path_checked") is True,
        "public_api_path": "ooxml-engine apply + MCP ooxml_apply",
        "public_path_replay_row_id": replay.get("row_id", ""),
    }


def _row_id(src: dict[str, Any], base: dict[str, Any]) -> str:
    package = src.get("package_id") or base.get("package_id") or _package_id(src)
    part = src.get("part_name") or base.get("part_name") or "document"
    return f"{src.get('format', '')}|{package}|{part}|{src.get('stable_id', '')}"


def _package_id(row: dict[str, Any]) -> str:
    return row.get("row_id", "").split("|")[1] if "|" in row.get("row_id", "") else ""


def _part_name(row: dict[str, Any]) -> str:
    return "presentation" if row.get("format") == "pptx" else "document"


def _model_id(row: dict[str, Any]) -> str:
    return f"{row.get('family', 'semantic')}.p90.v1"


def _understanding(row: dict[str, Any]) -> str:
    if row.get("family") in {"text_container", "table_cell_text"}:
        return "business-semantic"
    if row.get("family") == "vendor_private_extension":
        return "structural-semantic"
    return "office-semantic"


def _sibling_count(p89: dict[str, Any], src: dict[str, Any]) -> int:
    if p89.get("sibling_unchanged") is True:
        return 0
    return int(src.get("sibling_unexpected_semantic_mutation_count", 1))


def _public_api_path(row: dict[str, Any]) -> str:
    if row.get("interface") == "cli":
        return "ooxml-engine apply"
    if row.get("interface") == "mcp":
        return "ooxml_apply"
    return "ooxml_operation_engine.JsonRpcServer.ooxml_apply"
