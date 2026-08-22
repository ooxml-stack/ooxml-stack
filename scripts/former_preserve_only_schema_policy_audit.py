#!/usr/bin/env python3
"""Audit hydrated campaign rows against the schema-guided value policy."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from lxml import etree

from former_preserve_only_value_policy import checked_requested_value, next_requested_value

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT.parent / "ooxml-native-corpus"
OUT = ROOT / "release-evidence/former-preserve-only-semantic-editability"
HYDRATED = OUT / "operation-hydration-ledger.jsonl"
PROMOTED = OUT / "promotion-rows.jsonl"
AUDIT = OUT / "schema-policy-audit.json"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = _candidate_rows(_read_jsonl(HYDRATED), _promoted_sources())
    result = audit_rows(rows[: args.limit] if args.limit else rows)
    result["eligible_hydrated_count"] = len(rows)
    if args.write:
        _write_json(Path(args.out), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.fail_on_reject and result["rejected_count"] else 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="0 means audit all eligible hydrated rows")
    parser.add_argument("--out", default=str(AUDIT))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fail-on-reject", action="store_true")
    return parser.parse_args(argv)


def audit_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cache: dict[tuple[str, str], tuple[etree._ElementTree, dict[str, str]]] = {}
    accepted = rejected = 0
    by_reason: Counter[str] = Counter()
    by_operation: Counter[str] = Counter()
    by_attribute: Counter[str] = Counter()
    examples: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        reason = _audit_row(row, index, cache)
        if reason:
            rejected += 1
            _count_reject(row, reason, by_reason, by_operation, by_attribute, examples)
        else:
            accepted += 1
    return _summary(len(rows), accepted, rejected, by_reason, by_operation, by_attribute, examples)


def _audit_row(row: dict[str, Any], index: int, cache: dict) -> str:
    try:
        before = _read_value(row, cache)
        requested = row.get("requested_semantic_value") or next_requested_value(before, index, row)
        checked_requested_value(before, requested, row)
    except Exception as exc:  # noqa: BLE001
        return str(exc).split(":", 1)[0]
    return ""


def _count_reject(row: dict[str, Any], reason: str, by_reason, by_operation, by_attribute, examples) -> None:
    attr = str(row.get("attribute_name", "")).rsplit("}", 1)[-1]
    by_reason[reason] += 1
    by_operation[row.get("operation_id", "")] += 1
    by_attribute[attr] += 1
    examples.setdefault(reason, _example(row))


def _summary(total, accepted, rejected, by_reason, by_operation, by_attribute, examples) -> dict[str, Any]:
    return {
        "schema_version": "former-preserve-only-schema-policy-audit-v1",
        "audited_row_count": total,
        "accepted_count": accepted,
        "rejected_count": rejected,
        "all_hydrated_policy_safe": rejected == 0,
        "rejection_by_reason": dict(by_reason.most_common()),
        "rejection_by_operation_top20": dict(by_operation.most_common(20)),
        "rejection_by_attribute_top20": dict(by_attribute.most_common(20)),
        "examples_by_reason": examples,
    }


def _candidate_rows(rows: list[dict[str, Any]], promoted: set[str]) -> list[dict[str, Any]]:
    candidates = []
    for row in rows:
        if row.get("operation_hydration_status") != "hydrated":
            continue
        if row.get("source_row_id") in promoted:
            continue
        if row.get("part_name", "").startswith(("customXml/", "docMetadata/")):
            continue
        candidates.append(row)
    return candidates


def _promoted_sources() -> set[str]:
    if not PROMOTED.exists():
        return set()
    return {row.get("source_row_id", "") for row in _read_jsonl(PROMOTED) if row.get("pass") is True}


def _read_value(row: dict[str, Any], cache: dict) -> str:
    tree, namespaces = _part(row, cache)
    nodes = tree.xpath(row["operation_target_selector"], namespaces=namespaces)
    if len(nodes) != 1:
        raise ValueError(f"selector matched {len(nodes)}")
    node = nodes[0]
    if row.get("attribute_name"):
        if row["operation_id"] == "alternate_content.choice.metadata.set_value":
            node = next(child for child in node if child.tag.endswith("}Choice"))
        return node.get(row["attribute_name"], "")
    return " ".join("".join(node.itertext()).split())


def _part(row: dict[str, Any], cache: dict) -> tuple[etree._ElementTree, dict[str, str]]:
    key = (row["input_file"], row["part_name"])
    if key not in cache:
        with ZipFile(CORPUS / row["input_file"]) as package:
            xml = package.read(row["part_name"])
        parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
        tree = etree.parse(BytesIO(xml), parser)
        cache[key] = (tree, _namespaces(tree.getroot()))
    return cache[key]


def _namespaces(root: etree._Element) -> dict[str, str]:
    return {key: value for node in root.iter() for key, value in node.nsmap.items() if key}


def _example(row: dict[str, Any]) -> dict[str, Any]:
    keys = ("row_id", "family", "operation_id", "qname", "attribute_name", "input_file", "part_name")
    return {key: row.get(key) for key in keys}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
