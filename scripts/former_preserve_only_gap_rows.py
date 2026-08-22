"""Object-level gap rows for former-preserve-only semantic promotion."""

from __future__ import annotations

import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from lxml import etree

from former_preserve_only_promoted_index import promoted_index
from semantic_blocker_reasons import is_explicit_unsupported, no_semantic_reason
from xml_selector_resolution import select_one


ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT.parent
CORPUS = PROJECTS / "ooxml-native-corpus"
P77_ROWS = ROOT / "release-evidence/p77/public-api-object-edit-rows.jsonl"
P77_SHARDS = ROOT / "release-evidence/p77/public-api-object-edit-rows-shards"
P90_SHARDS = ROOT / "release-evidence/p90/sh-semantic-editability-rows.jsonl.d"
CAMPAIGN_ROWS = ROOT / "release-evidence/former-preserve-only-semantic-editability/promotion-rows.jsonl"
AUDIT = ROOT / "release-evidence/p90/anti-false-pass-audit.json"
MC_CHOICE = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Choice"
SEMANTIC_KINDS = {
    "default_attr",
    "direct_attr",
    "direct_text",
    "direct_alternate_requires",
    "direct_creation_id",
    "direct_vml_path_metadata",
    "descendant_attr",
    "descendant_text",
}
DEFAULT_ATTR_QNAMES = {
    "{http://schemas.microsoft.com/office/drawing/2010/main}useLocalDpi": "val",
    "{http://schemas.microsoft.com/office/drawing/2008/diagram}cNvSpPr": "txBox",
    "{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}cNvSpPr": "txBox",
    "{http://schemas.openxmlformats.org/drawingml/2006/chartDrawing}cNvSpPr": "txBox",
    "{http://schemas.openxmlformats.org/officeDocument/2006/math}dispDef": "val",
    "{http://schemas.microsoft.com/office/word/2012/wordml}chartTrackingRefBased": "val",
    "{http://schemas.microsoft.com/office/drawing/2010/main}shadowObscured": "val",
    "{http://schemas.microsoft.com/office/word/2010/wordml}round": "val",
}


def build_gap_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    promoted = _promoted_source_row_ids()
    grouped, baseline = _remaining_rows(promoted)
    rows = [gap for key, part_rows in grouped.items() for gap in _classify_part(key, part_rows)]
    return rows, _summary(rows, baseline, len(promoted))


def _promoted_source_row_ids() -> set[str]:
    promoted: set[str] = set()
    for shard in sorted(P90_SHARDS.glob("part-*.jsonl")):
        with shard.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                source = row.get("source_row_id", "")
                if row.get("source_phase") == "p80" and row.get("pass") is True and source.startswith("p80|"):
                    promoted.add(source[4:])
    promoted.update(_campaign_promoted_source_row_ids())
    return promoted


def _campaign_promoted_source_row_ids() -> set[str]:
    promoted, _ = promoted_index(CAMPAIGN_ROWS)
    return {source.removeprefix("p80|") for source in promoted if source}


def _remaining_rows(promoted: set[str]) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], int]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    baseline = 0
    for line in _p77_lines():
        row = json.loads(line)
        baseline += 1
        if row["row_id"] not in promoted:
            grouped[(row["input_file"], row["part_name"])].append(_keep_row(row))
    return grouped, baseline


def _p77_lines():
    paths = [P77_ROWS] if P77_ROWS.exists() else sorted(P77_SHARDS.glob("*.jsonl"))
    if not paths:
        raise FileNotFoundError("missing P77 rows; install LFS files or restore local public-api-object-edit-rows.jsonl")
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            yield from stream


def _keep_row(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "row_id",
        "format",
        "input_file",
        "package_id",
        "part_name",
        "stable_id",
        "selector",
        "qname",
        "family",
        "source_bucket",
        "operation_id",
        "before_canonical_xml_digest",
        "before_digest",
    )
    return {key: row.get(key, "") for key in keys}


def _classify_part(key: tuple[str, str], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    input_file, part_name = key
    try:
        root = _part_root(input_file, part_name)
    except Exception:
        return [_gap_row(row, "parse_fail") for row in rows]
    tree, namespaces = root.getroottree(), _namespaces(root)
    return [_gap_row(row, _row_kind(tree, namespaces, row)) for row in rows]


def _row_kind(tree: etree._ElementTree, namespaces: dict[str, str], row: dict[str, Any]) -> str:
    try:
        matches = tree.xpath(row["selector"], namespaces=namespaces)
    except Exception:
        matches = []
    matches = select_one(matches, row)
    if len(matches) != 1 or not isinstance(matches[0], etree._Element):
        return "resolve_fail"
    direct = _direct_kind(matches[0], row)
    return direct if direct != "no_direct" else _descendant_kind(matches[0])


def _direct_kind(element: etree._Element, row: dict[str, Any]) -> str:
    choice = next((child for child in element if child.tag == MC_CHOICE), None)
    if row["family"] == "alternate_content" and choice is not None and choice.get("Requires"):
        return "direct_alternate_requires"
    if row["family"] == "office_extension" and row.get("qname", "").endswith("}creationId") and "id" in element.attrib:
        return "direct_creation_id"
    if DEFAULT_ATTR_QNAMES.get(row.get("qname", "")):
        return "default_attr"
    if _safe_attr(element):
        return "direct_attr"
    if _text(element):
        return "direct_text"
    if row["family"] == "vml_drawing" and row.get("qname", "").endswith("}path"):
        return "direct_vml_path_metadata"
    return "no_direct"


def _descendant_kind(element: etree._Element) -> str:
    for node in element.iterdescendants():
        if _safe_attr(node):
            return "descendant_attr"
    for node in element.iterdescendants():
        if _text(node):
            return "descendant_text"
    return "no_descendant_value"


def _part_root(input_file: str, part_name: str) -> etree._Element:
    with zipfile.ZipFile(CORPUS / input_file) as package:
        return etree.fromstring(package.read(part_name))


def _safe_attr(element: etree._Element) -> str:
    for name in element.attrib:
        low = name.lower()
        local = low.rsplit("}", 1)[-1]
        if local != "id" and not any(token in low for token in ("rel", "macro", "textlink", "minver")):
            return name
    return ""


def _text(element: etree._Element) -> str:
    return " ".join("".join(element.itertext()).split())


def _namespaces(root: etree._Element) -> dict[str, str]:
    namespaces = {key: value for node in root.iter() for key, value in node.nsmap.items() if key}
    if "http://www.w3.org/2001/XMLSchema" in namespaces.values():
        namespaces.setdefault("xs", "http://www.w3.org/2001/XMLSchema")
        namespaces.setdefault("xsd", "http://www.w3.org/2001/XMLSchema")
    return namespaces


def _gap_row(row: dict[str, Any], semantic_kind: str) -> dict[str, Any]:
    blocker = _blocker(semantic_kind, row)
    return {
        "row_id": f"{row['format']}|{row['package_id']}|{row['part_name']}|{row['stable_id']}",
        "format": row["format"],
        "input_file": row["input_file"],
        "package_id": row["package_id"],
        "part_name": row["part_name"],
        "stable_id": row["stable_id"],
        "selector": row["selector"],
        "qname": row["qname"],
        "family": row["family"],
        "current_tier": "surface-editable",
        "missing_proof": _missing_proof(blocker),
        "blocker_type": blocker,
        "blocker_detail": _detail(blocker, semantic_kind),
        "next_operation_model": _next_operation(row["family"], blocker),
        "required_oracle": _required_oracle(blocker),
        "owner_repo": "ooxml-test-framework",
        "priority": _priority(row["family"], blocker),
        "status": "todo",
        "semantic_value_kind": semantic_kind,
        "source_row_id": row["row_id"],
        "source_bucket": row.get("source_bucket", ""),
    }


def _blocker(kind: str, row: dict[str, Any]) -> str:
    if kind in SEMANTIC_KINDS:
        return "semantic_value_available_pending_proof"
    if kind in {"resolve_fail", "parse_fail"}:
        return "resolve_failure"
    return no_semantic_reason(row)


def _missing_proof(blocker: str) -> list[str]:
    if blocker == "resolve_failure":
        return ["stable_selector", "parser"]
    if blocker == "no_semantic_value":
        return ["semantic_model", "semantic_value"]
    if is_explicit_unsupported(blocker):
        return ["dedicated_family_model", "safe_semantic_operation"]
    return ["semantic_replay", "exact_oracle", "public_cli_path", "public_mcp_path", "office_bound_oracle", "manifest_lock"]


def _detail(blocker: str, kind: str) -> str:
    if blocker == "resolve_failure":
        return f"stable selector or XML parse failed ({kind})"
    if blocker == "no_semantic_value":
        return "no owned semantic value modeled"
    if is_explicit_unsupported(blocker):
        return f"explicit unsupported reason: {blocker}"
    return f"semantic value kind {kind} exists but full object-level proof is not locked"


def _next_operation(family: str, blocker: str) -> str:
    if blocker == "resolve_failure":
        return f"{family}.stable_selector.resolve"
    if blocker == "no_semantic_value":
        return f"{family}.semantic_value.model"
    if is_explicit_unsupported(blocker):
        return f"{family}.{blocker}.model"
    return f"{family}.semantic_replay.prove"


def _required_oracle(blocker: str) -> str:
    if blocker == "resolve_failure":
        return "exactly one object resolves, stale and ambiguous handles reject"
    if blocker == "no_semantic_value":
        return "extract before/requested/after semantic value for an owned field"
    if is_explicit_unsupported(blocker):
        return "dedicated family model or explicit unsupported contract before promotion"
    return "exact after-value, sibling semantic safety, CLI/MCP replay, Office-bound output proof"


def _priority(family: str, blocker: str) -> str:
    if blocker == "semantic_value_available_pending_proof" or family == "office_extension":
        return "p0"
    return "p1"


def _summary(rows: list[dict[str, Any]], baseline: int, promoted: int) -> dict[str, Any]:
    by_blocker = Counter(row["blocker_type"] for row in rows)
    by_family = Counter(row["family"] for row in rows)
    by_qname = Counter(row["qname"] for row in rows)
    audit = _read_json(AUDIT)
    office = audit.get("office_freshness", {})
    metrics = audit.get("metrics", {})
    return {
        "former_preserve_only_denominator": baseline,
        "semantic_editable_count": promoted,
        "semantic_editable_remaining": len(rows),
        "remaining_by_blocker": dict(sorted(by_blocker.items())),
        "remaining_by_family": dict(by_family.most_common()),
        "remaining_by_qname_top20": dict(by_qname.most_common(20)),
        "remaining_by_owner_repo": {"ooxml-test-framework": len(rows)},
        "anti_false_pass_gate": audit.get("gate_pass", False),
        "full_semantic_claim_proven": False,
        "office_blocker_count": office.get("p80_office_blocker_count", "n/a"),
        "cli_path_unchecked_count": metrics.get("p90_cli_path_unchecked_count", "n/a"),
        "mcp_path_unchecked_count": metrics.get("p90_mcp_path_unchecked_count", "n/a"),
        "object_level_gap_rows_materialized": baseline - promoted == len(rows),
        "object_level_gap_row_count": len(rows),
        "aggregate_gap_row_count": 0,
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
