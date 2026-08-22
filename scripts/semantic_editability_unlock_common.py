"""Shared helpers for semantic-editability unlock planning."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release-evidence/former-preserve-only-semantic-editability"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def local_name(qname: str) -> str:
    if qname.startswith("{"):
        return qname.rsplit("}", 1)[-1]
    return qname.rsplit(":", 1)[-1]


def namespace(qname: str) -> str:
    return qname[1:].split("}", 1)[0] if qname.startswith("{") else ""


def counts(rows: Iterable[dict[str, Any]], field: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = str(row.get(field) or "<none>")
        counter[value] += 1
    return dict(counter.most_common())


def nested_counts(rows: Iterable[dict[str, Any]], left: str, right: str) -> dict[str, dict[str, int]]:
    grouped: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        grouped[str(row.get(left) or "<none>")][str(row.get(right) or "<none>")] += 1
    return {key: dict(value.most_common()) for key, value in sorted(grouped.items())}


def table(title: str, headers: tuple[str, ...], rows: Iterable[Iterable[Any]]) -> list[str]:
    lines = [f"## {title}", "", "| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        cells = [str(cell).replace("|", "\\|") for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
    return lines + [""]


def hydrated_by_row_id() -> dict[str, dict[str, Any]]:
    return {row["row_id"]: row for row in read_jsonl(EVIDENCE / "operation-hydration-ledger.jsonl")}


def joined_remaining_rows() -> list[dict[str, Any]]:
    hydrated = hydrated_by_row_id()
    rows = []
    for row in read_jsonl(EVIDENCE / "gap-ledger.jsonl"):
        extra = hydrated.get(row["row_id"], {})
        rows.append({**row, **_hydration_fields(extra)})
    return rows


def _hydration_fields(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "operation_hydration_status",
        "operation_id",
        "attribute_name",
        "before_semantic_value",
        "value_kind",
        "operation_target_selector",
    )
    return {key: row.get(key, "") for key in keys}


def value_kind(value: str, attr: str) -> str:
    lower_attr = attr.lower()
    lower = value.lower()
    if lower_attr.endswith("id") or "id" in lower_attr:
        return "identity_like"
    if lower_attr in {"embed", "link", "href"} or lower.startswith("rid"):
        return "relationship_like"
    if lower in {"true", "false", "0", "1"}:
        return "boolean_like"
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return "integer_like"
    if _is_hex_color(value):
        return "color_like"
    if value:
        return "text_or_enum_like"
    return "empty"


def _is_hex_color(value: str) -> bool:
    return len(value) in {6, 8} and all(ch in "0123456789abcdefABCDEF" for ch in value)


def why_remaining(row: dict[str, Any], office: set[str], timeout: set[str]) -> str:
    package = str(row.get("package_id", ""))
    blocker = str(row.get("blocker_type", ""))
    status = str(row.get("operation_hydration_status", ""))
    if package in office:
        return "native Office boundary evidence exists for this package; fresh exact-output pass is required"
    if package in timeout:
        return "prior replay timeout means this needs smaller scoped chunks before promotion"
    if blocker == "semantic_value_available_pending_proof" and status == "hydrated":
        return "semantic value exists, but row-level API/CLI/MCP/Office proof is not locked yet"
    if blocker == "semantic_value_available_pending_proof":
        return "semantic value bucket exists, but no promotable operation row is hydrated yet"
    return blocker_why(blocker)


def blocker_why(blocker: str) -> str:
    mapping = {
        "relationship_identity_like": "identity or relationship fields can break cross-part ownership if edited blindly",
        "binary_payload_reference": "binary payload references need a relationship and payload oracle before mutation",
        "needs_family_model": "the object has no dedicated semantic model or safe operation contract yet",
        "needs_vendor_family_model": "vendor-private fields need an explicit vendor family model before mutation",
    }
    return mapping.get(blocker, "remaining reason is recorded but needs a stricter unlock policy")


def boundary_package_ids(summary: dict[str, Any]) -> set[str]:
    return {str(row.get("package_id", "")) for row in summary.get("known_boundary_packages", [])}


def replay_timeout_package_ids(summary: dict[str, Any]) -> set[str]:
    return {str(row.get("package_id", "")) for row in summary.get("known_replay_timeout_packages", [])}


def sample_values(rows: Iterable[dict[str, Any]], limit: int = 5) -> list[str]:
    seen = []
    for row in rows:
        value = str(row.get("before_semantic_value", ""))
        if value and value not in seen:
            seen.append(value)
        if len(seen) == limit:
            break
    return seen


def policy_action(attr: str, qname: str, value_type: str, reason: str) -> tuple[str, str]:
    local = local_name(qname).lower()
    attr_l = attr.lower()
    identity = value_type in {"identity_like", "relationship_like"} or local.endswith("id") or attr_l.endswith("id")
    if identity or local in {"svgblip", "blip"}:
        return "keep_blocked", "identity, relationship, or binary-reference edits need stronger ownership or payload oracle"
    if _is_safe_string_candidate(qname, attr):
        return "unlock_now", "allowlisted non-visual object name string with exact row proof and Office pass required"
    if value_type in {"integer_like", "color_like", "empty"} or "integer" in reason:
        return "needs_spec_check", "typed numeric/color fields need schema bounds or parser-backed oracle before unlock"
    if value_type == "boolean_like":
        return "unlock_now", "field can use exact before/requested/after oracle plus Office pass without broad semantics"
    return "needs_spec_check", "text or enum-like metadata needs an explicit allowlist before unlock"


def _is_safe_string_candidate(qname: str, attr: str) -> bool:
    key = (namespace(qname), local_name(qname), local_name(attr))
    return key in {
        ("http://schemas.microsoft.com/office/drawing/2008/diagram", "spTree", "name"),
        ("http://schemas.microsoft.com/office/drawing/2008/diagram", "drawing", "name"),
        ("http://schemas.openxmlformats.org/drawingml/2006/chartDrawing", "sp", "name"),
    }


def family_model_template(family: str) -> dict[str, Any]:
    templates = {
        "office_extension": ("Office extension metadata", "allowlisted metadata attributes", "identity/reference/binary payload fields"),
        "vml_drawing": ("legacy VML drawing object", "text and metadata fields", "geometry without layout oracle"),
        "math_object": ("OMML math object", "token text and run text", "math tree restructuring"),
        "office_chart_extension": ("Office chart extension metadata", "known chart metadata", "chart data series edits"),
        "chart_drawing": ("chart drawing surface", "shape/title metadata", "chart data or geometry"),
        "custom_xml_schema": ("custom XML schema declaration", "safe schema annotations", "schema structural changes"),
        "custom_xml_payload": ("custom XML payload", "leaf text nodes", "mixed-content subtree rewrite"),
        "wps_extension": ("WPS vendor extension", "allowlisted vendor fields", "unmodeled vendor-private semantics"),
        "legacy_office_drawing": ("legacy Office drawing metadata", "known lock/wrap metadata", "binary or geometry internals"),
        "alternate_content": ("markup compatibility branch wrapper", "choice metadata", "fallback branch deletion or rewrite"),
    }
    subject, editable, disallowed = templates.get(family, ("OOXML extension object", "allowlisted metadata", "unmodeled internals"))
    return {"user_terms": subject, "editable_fields": editable, "disallowed_fields": disallowed}
