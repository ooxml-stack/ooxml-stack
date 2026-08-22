"""Build the authoritative row-level VML completion inventory."""

from __future__ import annotations

import argparse
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from lxml import etree
from ooxml_spec import SpecQuery

from former_preserve_only_gap_rows import _p77_lines, _promoted_source_row_ids
from former_preserve_only_promoted_index import promoted_index, row_target_key
from xml_selector_resolution import select_one


ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT.parent
EVIDENCE = ROOT / "release-evidence/former-preserve-only-semantic-editability"
CORPUS = PROJECTS / "ooxml-native-corpus"
HYDRATION = EVIDENCE / "operation-hydration-ledger.jsonl"
PROMOTIONS = EVIDENCE / "promotion-rows.jsonl"
OFFICE = EVIDENCE / "office-results"
PREFIXES = {
    "urn:schemas-microsoft-com:vml": "v",
    "urn:schemas-microsoft-com:office:office": "o",
    "urn:schemas-microsoft-com:office:word": "w10",
}
BOUNDARY = {"close_error", "timeout", "repair_dialog", "unreadable_content", "pass_with_dialog", "office_crash"}


def _jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def _canonical_id(row: dict[str, Any]) -> str:
    return "|".join((row["format"], row["package_id"], row["part_name"], row["stable_id"]))


def _hydration_index() -> dict[str, dict[str, Any]]:
    return {row["row_id"]: row for row in _jsonl(HYDRATION) if row.get("family") == "vml_drawing"}


def _promotion_indexes() -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str, str, str], dict[str, Any]]]:
    sources, targets = {}, {}
    for row in _jsonl(PROMOTIONS):
        if row.get("family") != "vml_drawing" or row.get("pass") is not True:
            continue
        source = row.get("source_row_id", "").removeprefix("p80|")
        if source:
            sources[source] = row
        params = row.get("operation_params", {})
        attribute = "" if row.get("operation_id") == "vml.formula.eqn.set_value" else params.get("attribute_name", "")
        key = (row.get("package_id", ""), row.get("operation_id", ""), row.get("operation_target", ""), attribute)
        targets.setdefault(key, row)
    return sources, targets


def _result_status(data: dict[str, Any]) -> str:
    statuses = [item.get("status", "") for item in data.get("results", [])]
    if len(statuses) == 1:
        return statuses[0]
    by_status = data.get("summary", {}).get("by_status", {})
    return next(iter(by_status), "") if len(by_status) == 1 else "mixed"


def _office_index(packages: set[str]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for path in sorted(OFFICE.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        text = path.name + " " + " ".join(str(item.get("file", "")) for item in data.get("results", []))
        timestamp = data.get("meta", {}).get("timestamp", "")
        for package in packages:
            if package not in text or timestamp < result.get(package, {}).get("timestamp", ""):
                continue
            result[package] = {"timestamp": timestamp, "status": _result_status(data), "evidence": str(path.relative_to(ROOT))}
    return result


def _namespaces(root: etree._Element) -> dict[str, str]:
    return {key: value for node in root.iter() for key, value in node.nsmap.items() if key}


def _element_snapshot(row: dict[str, Any], cache: dict[tuple[str, str], etree._ElementTree]) -> dict[str, Any]:
    key = (row["input_file"], row["part_name"])
    if key not in cache:
        with zipfile.ZipFile(CORPUS / key[0]) as package:
            cache[key] = etree.fromstring(package.read(key[1])).getroottree()
    tree = cache[key]
    try:
        matches = tree.xpath(row["selector"], namespaces=_namespaces(tree.getroot()))
    except etree.XPathError:
        matches = []
    matches = select_one(matches, row)
    if len(matches) != 1 or not isinstance(matches[0], etree._Element):
        return {"resolve_status": "failed", "attributes": {}, "direct_text": ""}
    node = matches[0]
    text = " ".join((node.text or "").split())
    return {"resolve_status": "resolved", "attributes": dict(sorted(node.attrib.items())), "direct_text": text}


def _spec_snapshot(qname: str, spec: SpecQuery) -> dict[str, Any]:
    uri, local = qname[1:].split("}", 1) if qname.startswith("{") else ("", qname)
    prefix = PREFIXES.get(uri, "")
    type_name = spec.find_element(f"{prefix}:{local}") if prefix else None
    qualified = f"{prefix}:{type_name}" if type_name and ":" not in type_name else type_name
    attrs = spec.resolved_attributes(qualified) if qualified else []
    return {"element_type": qualified or "", "attributes": {item["name"]: item.get("type", "") for item in attrs}}


def _state(row: dict[str, Any], hydration: dict[str, Any], office: dict[str, str], promoted: bool, spec: dict[str, Any]) -> str:
    if promoted:
        return "already_promoted"
    blocker = hydration.get("blocker_type", "")
    status = hydration.get("operation_hydration_status", "")
    reason = hydration.get("operation_hydration_reason", "")
    attr = hydration.get("attribute_name", "").lower()
    if blocker != "semantic_value_available_pending_proof":
        return "terminal_unsupported" if blocker else "no_semantic_value"
    if any(token in attr or token in reason for token in ("id", "rel", "reference", "imagedata")):
        return "identity_or_reference"
    terminal = _terminal_state(row.get("qname", ""), attr, reason)
    if terminal:
        return terminal
    if "style" in attr or "geometry" in reason:
        return "structurally_coupled"
    if status == "hydrated":
        return "ready_for_canary" if office.get("status") == "pass" else "office_boundary"
    return "needs_operation" if spec.get("element_type") else "needs_spec_resolution"


def _terminal_state(qname: str, attr: str, reason: str) -> str:
    local = qname.rsplit("}", 1)[-1]
    attr_local = attr.rsplit("}", 1)[-1]
    if local == "shape" and attr_local in {"type", "spt"}:
        return "identity_or_reference"
    if not attr and local in {"fill", "stroke", "path"}:
        return "no_semantic_value"
    coupled = {
        ("shapetype", "coordsize"), ("textbox", "inset"), ("handles", "position"),
        ("h", "position"), ("path", "connectlocs"), ("path", "connecttype"),
        ("group", "editas"),
    }
    if (local, attr_local) in coupled:
        return "structurally_coupled"
    if local == "group" and attr == "alt":
        return "terminal_unsupported"
    if local == "textbox" and ("descendant" in reason or attr not in {"inset"}):
        return "terminal_unsupported"
    return ""


def _terminal_reason(state: str, qname: str, attr: str) -> str:
    if state == "already_promoted" or state == "ready_for_canary":
        return ""
    local = qname.rsplit("}", 1)[-1]
    field = attr.rsplit("}", 1)[-1] or "empty-container"
    return f"{state}:{local}@{field}"


def _inventory_row(
    row: dict[str, Any], promoted: set[str], promoted_targets: set[tuple[str, str, str, str]],
    campaigns: dict[str, dict[str, Any]], target_campaigns: dict[tuple[str, str, str, str], dict[str, Any]],
    hydrations: dict[str, dict[str, Any]],
    office: dict[str, dict[str, str]], spec: SpecQuery, cache: dict[tuple[str, str], etree._ElementTree],
) -> dict[str, Any]:
    source = row["row_id"]
    canonical = _canonical_id(row)
    hydration = hydrations.get(canonical, {})
    target_key = row_target_key(hydration)
    campaign = campaigns.get(source, {}) or target_campaigns.get(target_key, {})
    spec_data = _spec_snapshot(row["qname"], spec)
    office_data = office.get(row["package_id"], {})
    is_promoted = source in promoted or target_key in promoted_targets
    evidence = [campaign.get("office_result_id", "")] if campaign else []
    if office_data.get("evidence"):
        evidence.append(office_data["evidence"])
    state = _state(row, hydration, office_data, is_promoted, spec_data)
    if state not in {"already_promoted", "ready_for_canary"}:
        evidence.append("scripts/build_vml_completion_inventory.py")
    return {
        "row_id": canonical, "source_row_id": source, "format": row["format"], "input_file": row["input_file"],
        "package_id": row["package_id"], "part_name": row["part_name"], "qname": row["qname"],
        "selector": row["selector"], "attribute_name": hydration.get("attribute_name", ""),
        "current_value": _element_snapshot(row, cache), "operation_id": campaign.get("operation_id", hydration.get("operation_id", "")),
        "schema": spec_data, "parser_backed_field": hydration.get("semantic_value_kind", ""),
        "latest_office": office_data, "state": state,
        "terminal_reason": _terminal_reason(state, row["qname"], hydration.get("attribute_name", "")),
        "next_action": hydration.get("operation_hydration_reason", "") or hydration.get("next_operation_model", ""),
        "terminal_evidence_paths": sorted({item for item in evidence if item}),
    }


def build_inventory() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_rows = [json.loads(line) for line in _p77_lines()]
    vml_rows = [row for row in source_rows if row.get("family") == "vml_drawing"]
    packages = {row["package_id"] for row in vml_rows}
    promoted, promoted_targets = _promoted_source_row_ids(), promoted_index(PROMOTIONS)[1]
    campaigns, target_campaigns = _promotion_indexes()
    hydrations, office = _hydration_index(), _office_index(packages)
    spec, cache = SpecQuery(), {}
    rows = [
        _inventory_row(row, promoted, promoted_targets, campaigns, target_campaigns, hydrations, office, spec, cache)
        for row in vml_rows
    ]
    rows.sort(key=lambda item: item["row_id"])
    counts = Counter(row["state"] for row in rows)
    summary = {"schema_version": "ooxml-vml-completion-inventory-v1", "row_count": len(rows),
               "unique_row_count": len({row["row_id"] for row in rows}), "state_counts": dict(sorted(counts.items()))}
    summary["invariant_pass"] = summary["row_count"] == 3314 == summary["unique_row_count"] == sum(counts.values())
    return rows, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    rows, summary = build_inventory()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["invariant_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
