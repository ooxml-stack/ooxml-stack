"""Classify P80 former-preserve-only rows by semantic value availability."""

from __future__ import annotations

import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from lxml import etree

ROOT = Path(__file__).resolve().parents[3]
STACK = ROOT / "ooxml-stack"
CORPUS = ROOT / "ooxml-native-corpus"
ROWS = STACK / "release-evidence/p77/public-api-object-edit-rows.jsonl"
OUT = STACK / "release-evidence/p90/p80-semantic-promotion-feasibility.json"
MC_CHOICE = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Choice"
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


def main() -> int:
    artifact = build_artifact()
    OUT.write_text(json.dumps(artifact, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def build_artifact() -> dict[str, Any]:
    counts: Counter[str] = Counter()
    families: dict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, dict[str, Any]] = {}
    for key, rows in _rows_by_part().items():
        _classify_part(key, rows, counts, families, samples)
    return _artifact(counts, families, samples)


def _rows_by_part() -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    with ROWS.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            grouped[(row["input_file"], row["part_name"])].append(row)
    return grouped


def _classify_part(key, rows, counts, families, samples) -> None:
    input_file, part_name = key
    try:
        root = _part_root(input_file, part_name)
    except Exception:
        _count_fail(rows, counts, families, samples, "parse_fail")
        return
    tree, namespaces = root.getroottree(), _namespaces(root)
    for row in rows:
        kind = _row_kind(tree, namespaces, row)
        counts[kind] += 1
        families[row["family"]][kind] += 1
        samples.setdefault(f"{row['family']}:{kind}", _sample(row))


def _row_kind(tree: etree._ElementTree, namespaces: dict[str, str], row: dict[str, Any]) -> str:
    try:
        matches = tree.xpath(row["selector"], namespaces=namespaces)
    except Exception:
        matches = []
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
    if _default_attr(row):
        return "default_attr"
    if _safe_attr(element):
        return "direct_attr"
    if _text(element):
        return "direct_text"
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


def _default_attr(row: dict[str, Any]) -> str:
    return DEFAULT_ATTR_QNAMES.get(row.get("qname", ""), "")


def _namespaces(root: etree._Element) -> dict[str, str]:
    return {key: value for node in root.iter() for key, value in node.nsmap.items() if key}


def _count_fail(rows, counts, families, samples, kind: str) -> None:
    for row in rows:
        counts[kind] += 1
        families[row["family"]][kind] += 1
        samples.setdefault(f"{row['family']}:{kind}", _sample(row))


def _sample(row: dict[str, Any]) -> dict[str, Any]:
    keys = ("row_id", "family", "qname", "selector", "input_file", "part_name")
    return {key: row.get(key, "") for key in keys}


def _artifact(counts: Counter[str], families: dict[str, Counter[str]], samples: dict[str, dict[str, Any]]) -> dict[str, Any]:
    semantic = sum(
        counts[key]
        for key in (
            "default_attr",
            "direct_attr",
            "direct_text",
            "direct_alternate_requires",
            "direct_creation_id",
            "descendant_attr",
            "descendant_text",
        )
    )
    return {
        "schema_version": "p90-p80-semantic-promotion-feasibility-v1",
        "p80_row_count": sum(counts.values()),
        "semantic_value_available_count": semantic,
        "semantic_value_missing_count": counts["no_descendant_value"],
        "resolve_or_parse_failure_count": counts["resolve_fail"] + counts["parse_fail"],
        "direct_or_owned_value_counts": dict(sorted(counts.items())),
        "family_counts": {family: dict(sorted(counter.items())) for family, counter in sorted(families.items())},
        "samples": samples,
        "blocks_full_p90_claim": counts["no_descendant_value"] > 0 or counts["resolve_fail"] > 0 or counts["parse_fail"] > 0,
    }


if __name__ == "__main__":
    raise SystemExit(main())
