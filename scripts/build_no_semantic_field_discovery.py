#!/usr/bin/env python3
"""Discover next actions for rows with no target semantic scalar."""

from __future__ import annotations

import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from lxml import etree

from semantic_editability_unlock_common import EVIDENCE, read_jsonl, table, write_json, write_md
from xml_selector_resolution import select_one

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT.parent / "ooxml-native-corpus"
OUT_JSON = EVIDENCE / "no-semantic-field-discovery.json"
OUT_MD = EVIDENCE / "no-semantic-field-discovery.md"


def main() -> int:
    rows = read_jsonl(EVIDENCE / "gap-ledger.jsonl")
    summary = build_discovery(rows, CORPUS)
    write_json(OUT_JSON, summary)
    write_md(OUT_MD, markdown(summary))
    print({"discovery": str(OUT_JSON), "dashboard": str(OUT_MD)})
    return 0


def build_discovery(rows: list[dict[str, Any]], corpus: Path, sample_limit: int = 5) -> dict[str, Any]:
    targets = [row for row in rows if _is_no_semantic_field(row)]
    inspected = _inspect_rows(targets, corpus)
    groups = _group_rows(inspected, sample_limit)
    actions = Counter(row["recommended_action"] for row in inspected)
    classes = Counter(row["classification"] for row in inspected)
    return {
        "schema_version": "no-semantic-field-discovery-v1",
        "input_row_count": len(targets),
        "classification_counts": dict(classes.most_common()),
        "recommended_action_counts": dict(actions.most_common()),
        "investigation_group_count": sum(group["recommended_action"] != "keep_unsupported" for group in groups),
        "groups": groups,
    }


def _is_no_semantic_field(row: dict[str, Any]) -> bool:
    hard = {"relationship_identity_like", "binary_payload_reference", "needs_vendor_family_model"}
    return row.get("semantic_value_kind") == "no_descendant_value" and row.get("blocker_type") not in hard


def _inspect_rows(rows: list[dict[str, Any]], corpus: Path) -> list[dict[str, Any]]:
    cache: dict[tuple[str, str], etree._Element | None] = {}
    return [_inspect_row(row, corpus, cache) for row in rows]


def _inspect_row(row: dict[str, Any], corpus: Path, cache: dict[tuple[str, str], etree._Element | None]) -> dict[str, Any]:
    key = (str(row.get("input_file", "")), str(row.get("part_name", "")))
    root = cache.setdefault(key, _part_root(corpus, *key))
    element = _resolve(row, root)
    if element is None:
        return _row_result(row, "unresolved_target", "recheck_selector", {})
    facts = _element_facts(element)
    classification = _classify(facts)
    action = _action(classification)
    return _row_result(row, classification, action, facts)


def _part_root(corpus: Path, input_file: str, part_name: str) -> etree._Element | None:
    try:
        with zipfile.ZipFile(corpus / input_file) as package:
            return etree.fromstring(package.read(part_name))
    except Exception:
        return None


def _resolve(row: dict[str, Any], root: etree._Element | None) -> etree._Element | None:
    if root is None:
        return None
    try:
        matches = root.getroottree().xpath(str(row.get("selector", "")), namespaces=_namespaces(root))
    except Exception:
        return None
    matches = select_one(matches, row)
    if len(matches) != 1 or not isinstance(matches[0], etree._Element):
        return None
    return matches[0]


def _element_facts(element: etree._Element) -> dict[str, Any]:
    parent = element.getparent()
    target_attrs = _safe_attr_names(element)
    descendant_scalar = any(_has_scalar(node) for node in element.iterdescendants())
    sibling_scalar_tags = _sibling_scalar_tags(element)
    return {
        "target_attr_names": target_attrs,
        "target_has_text": _has_own_text(element),
        "target_child_count": len(element),
        "target_descendant_count": sum(1 for _ in element.iterdescendants()),
        "target_descendant_has_scalar": descendant_scalar,
        "parent_qname": parent.tag if parent is not None else "",
        "parent_attr_names": _safe_attr_names(parent) if parent is not None else [],
        "parent_has_text": _has_own_text(parent) if parent is not None else False,
        "sibling_scalar_count": len(sibling_scalar_tags),
        "sibling_scalar_qnames": sibling_scalar_tags[:5],
    }


def _classify(facts: dict[str, Any]) -> str:
    if facts["target_attr_names"] or facts["target_has_text"] or facts["target_descendant_has_scalar"]:
        return "unexpected_target_scalar"
    if facts["target_child_count"]:
        return "structural_subtree_without_scalar"
    if facts["parent_attr_names"] or facts["parent_has_text"] or facts["sibling_scalar_count"]:
        return "context_only_structural_container"
    return "empty_structural_container"


def _action(classification: str) -> str:
    if classification == "unexpected_target_scalar":
        return "rebuild_gap_or_add_policy"
    if classification == "context_only_structural_container":
        return "investigate_context_model"
    if classification == "unresolved_target":
        return "recheck_selector"
    return "keep_unsupported"


def _row_result(row: dict[str, Any], classification: str, action: str, facts: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_id": row.get("row_id", ""),
        "package_id": row.get("package_id", ""),
        "part_name": row.get("part_name", ""),
        "family": row.get("family", ""),
        "qname": row.get("qname", ""),
        "selector": row.get("selector", ""),
        "classification": classification,
        "recommended_action": action,
        **facts,
    }


def _group_rows(rows: list[dict[str, Any]], sample_limit: int) -> list[dict[str, Any]]:
    grouped: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["family"]), str(row["qname"]))].append(row)
    items = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    return [_group_summary(key, bucket, sample_limit) for key, bucket in items]


def _group_summary(key: tuple[str, str], rows: list[dict[str, Any]], sample_limit: int) -> dict[str, Any]:
    classes = Counter(row["classification"] for row in rows)
    actions = Counter(row["recommended_action"] for row in rows)
    return {
        "family": key[0],
        "qname": key[1],
        "count": len(rows),
        "classification_counts": dict(classes.most_common()),
        "recommended_action": actions.most_common(1)[0][0],
        "sample_rows": [_sample_row(row) for row in rows[:sample_limit]],
    }


def _sample_row(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "row_id",
        "package_id",
        "part_name",
        "classification",
        "recommended_action",
        "target_child_count",
        "sibling_scalar_count",
        "parent_qname",
        "sibling_scalar_qnames",
    )
    return {key: row.get(key, "") for key in keys}


def _safe_attr_names(element: etree._Element | None) -> list[str]:
    if element is None:
        return []
    names = []
    for name in element.attrib:
        low = name.lower()
        local = low.rsplit("}", 1)[-1]
        if local != "id" and not any(token in low for token in ("rel", "macro", "textlink", "minver")):
            names.append(_local_name(name))
    return names


def _sibling_scalar_tags(element: etree._Element) -> list[str]:
    parent = element.getparent()
    if parent is None:
        return []
    return [node.tag for node in parent if node is not element and _has_scalar(node)]


def _has_scalar(element: etree._Element) -> bool:
    if _safe_attr_names(element) or _has_own_text(element):
        return True
    return any(_safe_attr_names(node) or _has_own_text(node) for node in element.iterdescendants())


def _has_own_text(element: etree._Element | None) -> bool:
    return bool(element is not None and element.text and element.text.strip())


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1] if name.startswith("{") else name.rsplit(":", 1)[-1]


def _namespaces(root: etree._Element) -> dict[str, str]:
    return {key: value for node in root.iter() for key, value in node.nsmap.items() if key}


def markdown(summary: dict[str, Any]) -> str:
    lines = ["# No Semantic Field Discovery", ""]
    lines += [f"- Input rows: {summary['input_row_count']}"]
    lines += [f"- Investigation groups: {summary['investigation_group_count']}", ""]
    lines += _count_lines("Classification Counts", summary["classification_counts"])
    lines += _count_lines("Recommended Action Counts", summary["recommended_action_counts"])
    rows = summary["groups"][:40]
    lines += table(
        "Top Groups",
        ("Family", "QName", "Rows", "Action", "Classes"),
        [(row["family"], row["qname"], row["count"], row["recommended_action"], row["classification_counts"]) for row in rows],
    )
    return "\n".join(lines)


def _count_lines(title: str, counts: dict[str, int]) -> list[str]:
    return [f"## {title}", ""] + [f"- `{key}`: {value}" for key, value in counts.items()] + [""]


if __name__ == "__main__":
    raise SystemExit(main())
