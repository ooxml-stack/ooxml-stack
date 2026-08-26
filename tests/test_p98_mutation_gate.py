from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_p98_mutation_gate import run_gate


def test_p98_gate_proves_high_risk_uncovered_families(tmp_path: Path) -> None:
    summary = run_gate(tmp_path)

    assert summary["ok"] is True
    assert summary["mutation_case_count"] == 13
    assert summary["mutation_case_fail_count"] == 0
    assert summary["mutation_proven_format_rule_count"] == 13
    assert summary["mutation_proven_unique_rule_count"] == 12
    assert summary["formats"] == {
        "docx": {"total": 4, "passed": 4, "failed": 0},
        "pptx": {"total": 6, "passed": 6, "failed": 0},
        "xlsx": {"total": 3, "passed": 3, "failed": 0},
    }


def test_p98_covers_complex_families(tmp_path: Path) -> None:
    summary = run_gate(tmp_path)
    proven = {(row["format"], row["rule_id"]) for row in summary["cases"]}

    # ChartEx across pptx and docx.
    assert ("pptx", "chartex_mc_wrapper") in proven
    assert ("pptx", "chartex_style_id") in proven
    assert ("pptx", "chartex_strdim_order") in proven
    assert ("docx", "chartex_style_id") in proven
    # SmartArt / diagram relationship pairing.
    assert ("pptx", "smartart_drawing_part") in proven
    # Embedded package / media relationships.
    assert ("pptx", "chart_embedded_xlsx") in proven
    assert ("pptx", "media_rel_integrity") in proven
    assert ("docx", "hyperlink_rel_valid") in proven
    assert ("docx", "header_footer_rel_valid") in proven
    assert ("docx", "document_rels_required") in proven
    # Spreadsheet slicer contracts.
    assert ("xlsx", "workbook_slicer_cache_structure") in proven
    assert ("xlsx", "slicer_part_contract") in proven
    assert ("xlsx", "slicer_cache_definition_consistency") in proven


def test_p98_cases_are_newly_proven_rules(tmp_path: Path) -> None:
    # Every P98 target rule was left uncovered_in_p97, so P98 adds net new
    # mutation coverage rather than re-deriving P97.
    p97_proven = {
        "content_types_integrity", "image_rel_integrity", "color_no_hash",
        "table_grid_consistency", "wml_table_grid_consistency",
        "numbering_ref_valid", "body_required", "slide_rel_completeness",
        "blip_fill_integrity", "element_order", "animation_target_ref",
        "sheet_rid_resolvable", "rel_id_unique", "styles_rgb_argb_width",
        "sst_count_consistent", "cell_ref_matches_row",
    }
    summary = run_gate(tmp_path)
    p98_proven = {row["rule_id"] for row in summary["cases"] if row["status"] == "passed"}
    assert p98_proven == {
        "chartex_mc_wrapper", "chartex_style_id", "chartex_strdim_order",
        "smartart_drawing_part", "chart_embedded_xlsx", "media_rel_integrity",
        "hyperlink_rel_valid", "header_footer_rel_valid", "document_rels_required",
        "workbook_slicer_cache_structure", "slicer_part_contract",
        "slicer_cache_definition_consistency",
    }
    assert p98_proven.isdisjoint(p97_proven)


def test_p98_coverage_map_marks_uncovered_rules(tmp_path: Path) -> None:
    summary = run_gate(tmp_path)
    counts = summary["coverage_map"]["counts"]

    assert counts["docx"]["mutation_proven"] == 4
    assert counts["pptx"]["mutation_proven"] == 6
    assert counts["xlsx"]["mutation_proven"] == 3
    assert counts["docx"]["uncovered_in_p98"] > 0
    assert counts["pptx"]["uncovered_in_p98"] > 0
    assert counts["xlsx"]["uncovered_in_p98"] > 0


def test_p98_source_state_avoids_self_commit_pointer(tmp_path: Path) -> None:
    summary = run_gate(tmp_path)

    assert "ooxml-stack" not in summary["source_heads"]
    assert {row["path"] for row in summary["generator_source_files"]} == {
        "scripts/run_p98_mutation_gate.py",
        "scripts/p98_mutation_cases.py",
    }


def test_p98_writes_manifest_and_summary(tmp_path: Path) -> None:
    run_gate(tmp_path)

    summary = json.loads((tmp_path / "rule-coverage-mutation-gate-summary.json").read_text())
    manifest = json.loads((tmp_path / "manifest.json").read_text())

    assert summary["schema_version"] == "p98-rule-coverage-mutation-gate-v1"
    assert manifest["schema_version"] == "p98-evidence-manifest-v1"
    assert manifest["files"][0]["path"].endswith("rule-coverage-mutation-gate-summary.json")


def test_p98_release_profile_matches_generated_summary() -> None:
    root = Path(__file__).resolve().parents[1]
    summary = json.loads((root / "release-evidence/p98/rule-coverage-mutation-gate-summary.json").read_text())
    profile = json.loads((root / "release-profiles/p98-rule-coverage-mutation.json").read_text())

    assert profile["ok"] == summary["ok"]
    assert profile["expected_metrics"]["mutation_case_count"] == summary["mutation_case_count"]
    assert profile["expected_metrics"]["mutation_case_pass_count"] == summary["mutation_case_pass_count"]
    assert profile["expected_metrics"]["mutation_case_fail_count"] == summary["mutation_case_fail_count"]
    assert profile["expected_metrics"]["mutation_proven_format_rule_count"] == summary["mutation_proven_format_rule_count"]
    assert profile["expected_metrics"]["mutation_proven_unique_rule_count"] == summary["mutation_proven_unique_rule_count"]
    assert profile["expected_metrics"]["formats"] == summary["formats"]
    assert profile["coverage_counts"] == summary["coverage_map"]["counts"]