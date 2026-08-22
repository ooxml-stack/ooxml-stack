from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_capability_dashboard import build_dashboard
from build_ooxml_element_capability_ledger import build_ledger
from campaign_office_boundary_summary import failed_detail
from campaign_office_boundary_summary import primary_status
from former_preserve_only_promoted_index import alias_operation_count
from former_preserve_only_gap_rows import build_gap_rows
from former_preserve_only_gap_rows import _namespaces
from former_preserve_only_gap_rows import _p77_lines
from semantic_blocker_reasons import no_semantic_reason
from xml_selector_resolution import canonical_digest, select_one


@pytest.fixture(scope="module")
def ledger() -> dict[str, Any]:
    return build_ledger()


def test_ledger_is_json_serializable(ledger: dict[str, Any]) -> None:
    encoded = json.dumps(ledger, ensure_ascii=False)

    assert json.loads(encoded)["schema_version"] == "ooxml-element-capability-ledger-v1"


def test_required_top_level_sections_exist(ledger: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "generated_at",
        "unit_definitions",
        "claim_summary",
        "full_claim_proven",
        "levels",
        "tier_counts",
        "blockers",
        "families",
        "evidence_refs",
        "source_integrity",
        "code_gate_summary",
        "office_boundary_summary",
        "close_error_diagnostic_summary",
        "close_error_rerun_summary",
        "remaining_bucket_summary",
        "raw_sources",
    }

    assert required <= set(ledger)


def test_every_level_has_denominator_and_notes(ledger: dict[str, Any]) -> None:
    required = {"count", "unit", "denominator_kind", "strict_claim", "evidence_refs", "notes", "zh_notes"}

    for level in ledger["levels"].values():
        assert required <= set(level)
        assert level["unit"]
        assert level["denominator_kind"]
        assert level["notes"]
        assert level["zh_notes"]


def test_full_claim_stays_false_while_blockers_remain(ledger: dict[str, Any]) -> None:
    assert ledger["blockers"]["total"] > 0
    assert ledger["full_claim_proven"] is False


def test_schema_prefix_fix_clears_current_resolve_failures(ledger: dict[str, Any]) -> None:
    assert ledger["blockers"]["by_reason"].get("resolve_failure", 0) == 0


def test_no_semantic_value_rows_are_explicitly_reasoned(ledger: dict[str, Any]) -> None:
    reasons = ledger["blockers"]["by_reason"]

    assert reasons.get("no_semantic_value", 0) == 0
    assert reasons["relationship_identity_like"] > 0
    assert reasons["binary_payload_reference"] > 0
    assert reasons["needs_family_model"] > 0


def test_known_empty_reference_rows_get_specific_reasons() -> None:
    assert no_semantic_reason({"qname": "{urn:p14}sldId", "family": "office_extension"}) == "relationship_identity_like"
    assert no_semantic_reason({"qname": "{urn:asvg}svgBlip", "family": "office_extension"}) == "binary_payload_reference"


def test_p77_rows_can_read_lfs_shards(tmp_path, monkeypatch) -> None:
    shard_dir = tmp_path / "shards"
    shard_dir.mkdir()
    (shard_dir / "public-api-object-edit-rows-001.jsonl").write_text('{"row_id":"a"}\n')
    (shard_dir / "public-api-object-edit-rows-002.jsonl").write_text('{"row_id":"b"}\n')
    monkeypatch.setattr("former_preserve_only_gap_rows.P77_ROWS", tmp_path / "missing.jsonl")
    monkeypatch.setattr("former_preserve_only_gap_rows.P77_SHARDS", shard_dir)

    assert [json.loads(line)["row_id"] for line in _p77_lines()] == ["a", "b"]


def test_semantic_and_unproven_reconcile_to_surface_denominator(ledger: dict[str, Any]) -> None:
    levels = ledger["levels"]
    semantic = levels["semantic_editable"]["count"]
    unproven = levels["unsupported_or_not_proven"]["count"]

    assert semantic + unproven == levels["surface_editable"]["count"]


def test_ledger_uses_live_object_gap_summary(ledger: dict[str, Any]) -> None:
    _, summary = build_gap_rows()

    assert ledger["levels"]["semantic_editable"]["count"] == summary["semantic_editable_count"]
    assert ledger["levels"]["unsupported_or_not_proven"]["count"] == summary["semantic_editable_remaining"]


def test_office_files_are_not_object_rows(ledger: dict[str, Any]) -> None:
    office = ledger["levels"]["office_output_files"]
    semantic = ledger["levels"]["semantic_editable"]

    assert office["unit"] == "Office output files"
    assert office["denominator_kind"] != semantic["denominator_kind"]
    assert office["count"] != semantic["count"]


def test_office_boundary_failures_are_not_promoted(ledger: dict[str, Any]) -> None:
    boundary = ledger["office_boundary_summary"]

    assert boundary["candidate_rows_by_status"].get("close_error", 0) > 0
    assert boundary["candidate_rows_not_promoted_count"] >= boundary["candidate_rows_by_status"]["close_error"]
    assert boundary["candidate_rows_by_status"].get("pass", 0) != ledger["levels"]["semantic_editable"]["count"]
    assert all(row["package_id"] for row in boundary["failed_details"])
    assert all(row["office_result_path"].endswith(".json") for row in boundary["failed_details"])
    assert all("/" + "Users/" not in row["message_excerpt"] for row in boundary["failed_details"])


def test_manual_office_override_wins_over_auto_pass(tmp_path: Path) -> None:
    data = {
        "manual_override": {"status": "unreadable_content", "message": "manual Word open error"},
        "results": [{"file": "api-x-docx_pkg.docx", "status": "pass", "message": "auto pass"}],
    }
    office = tmp_path / "api-x-docx_pkg.json"

    assert primary_status(data) == "unreadable_content"
    detail = failed_detail(tmp_path, {}, office, data, primary_status(data), 0)
    assert detail["message_excerpt"] == "manual Word open error"


def test_claim_summary_carries_strict_numbers(ledger: dict[str, Any]) -> None:
    claim = ledger["claim_summary"]

    assert claim["surface_editable_count"] == ledger["levels"]["surface_editable"]["count"]
    assert claim["semantic_editable_count"] == ledger["levels"]["semantic_editable"]["count"]
    assert claim["semantic_blocker_count"] == ledger["blockers"]["total"]
    assert ledger["full_claim_proven"] is False
    assert claim["anti_false_pass_gate"] is False


def test_close_error_diagnostics_are_exposed_without_promotion_claim(ledger: dict[str, Any]) -> None:
    diagnostic = ledger["close_error_diagnostic_summary"]
    rerun = ledger["close_error_rerun_summary"]

    assert diagnostic["close_error_office_result_count"] >= rerun["office_only_rerun_count"]
    assert rerun["recovered_promoted_row_count"] == 0
    assert rerun["confirmed_boundary_count"] >= 0


def test_false_pass_counters_are_not_counted(ledger: dict[str, Any]) -> None:
    gates = ledger["code_gate_summary"]

    assert gates["aggregate_replay_object_row_count"] == 0
    assert gates["marker_only_mutation_row_count"] == 0
    assert gates["package_only_office_pass_row_count"] == 0
    assert gates["direct_mcp_function_call_count"] == 0


def test_live_alias_operations_are_exposed_not_promoted(ledger: dict[str, Any]) -> None:
    rows_path = Path("release-evidence/former-preserve-only-semantic-editability/promotion-rows.jsonl")
    alias_path = Path("release-evidence/former-preserve-only-semantic-editability/alias-operation-rows.jsonl")
    alias_count = alias_operation_count(rows_path)

    assert ledger["code_gate_summary"]["alias_operation_row_count"] == alias_count
    assert alias_count == 0
    assert ledger["code_gate_summary"]["alias_operation_evidence_row_count"] == _line_count(alias_path)


def test_alias_evidence_rows_do_not_block_zero_failure_gate(ledger: dict[str, Any]) -> None:
    gates = dict(ledger["code_gate_summary"])
    gates["anti_false_pass_gate"] = True
    blockers = {"total": 0}
    levels = {key: dict(value) for key, value in ledger["levels"].items()}
    levels["semantic_editable"]["count"] = levels["surface_editable"]["count"]

    from build_ooxml_element_capability_ledger import full_claim_proven

    assert full_claim_proven(levels, blockers, gates) is True


def test_gap_resolver_accepts_xsd_schema_prefix_alias() -> None:
    xml = (
        b'<ct:contentTypeSchema xmlns:ct="urn:ct" '
        b'xmlns:xsd="http://www.w3.org/2001/XMLSchema"><xsd:schema/></ct:contentTypeSchema>'
    )

    namespaces = _namespaces(etree.fromstring(xml))

    assert namespaces["xs"] == "http://www.w3.org/2001/XMLSchema"


def test_selector_resolution_uses_digest_for_duplicate_xpath_matches() -> None:
    root = etree.fromstring(b"<root><item a='1'/><item a='2'/></root>")
    matches = root.xpath("/root/item")
    row = {"before_canonical_xml_digest": canonical_digest(matches[1])}

    selected = select_one(matches, row)

    assert selected == [matches[1]]


def test_phase_paths_are_only_audit_references(ledger: dict[str, Any]) -> None:
    leaks = []
    for path, value in _strings(ledger):
        if _allowed_audit_path(path):
            continue
        if re.search(r"\bP\d+\b|release-evidence/p\d+", value):
            leaks.append((path, value))

    assert leaks == []


def test_dashboard_uses_capability_labels_not_phase_labels(ledger: dict[str, Any]) -> None:
    dashboard = build_dashboard(ledger)
    public_lines = [line for line in dashboard.splitlines() if "release-evidence/p" not in line]

    assert not re.search(r"\bP\d+\b", "\n".join(public_lines))
    assert "Capability Levels" in dashboard
    assert "Semantic Blockers" in dashboard
    assert "Anti-False-Pass Gate Scope" in dashboard
    assert "Campaign Office Boundary Scope" in dashboard
    assert "Campaign Office Boundary Details" in dashboard
    assert "Remaining Bucket Acceleration" in dashboard


def test_remaining_bucket_summary_is_linked_from_main_ledger(ledger: dict[str, Any]) -> None:
    summary = ledger["remaining_bucket_summary"]
    sources = ledger["raw_sources"]
    dashboard = build_dashboard(ledger)

    assert sources["remaining_bucket_summary"].endswith("remaining-bucket-summary.json")
    assert summary["schema_version"] == "semantic-editability-remaining-buckets-v1"
    assert summary["candidate_packages"]
    assert "| known_replay_timeout_package_count | 4 |" in dashboard
    assert "| known_replay_timeout_entry_count | 5 |" in dashboard
    assert "| known_replay_timeout_package_scope_count | 4 |" in dashboard
    assert "| known_replay_timeout_operation_scope_count | 1 |" in dashboard


def _strings(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
    if isinstance(value, str):
        return [(path, value)]
    if isinstance(value, dict):
        return [item for key, child in value.items() for item in _strings(child, (*path, str(key)))]
    if isinstance(value, list):
        return [item for index, child in enumerate(value) for item in _strings(child, (*path, str(index)))]
    return []


def _allowed_audit_path(path: tuple[str, ...]) -> bool:
    return "evidence_refs" in path or "raw_sources" in path


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
