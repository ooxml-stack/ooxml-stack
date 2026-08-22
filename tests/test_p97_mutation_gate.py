from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_p97_mutation_gate import run_gate


def test_p97_mutation_gate_proves_representative_rules(tmp_path: Path) -> None:
    summary = run_gate(tmp_path)

    assert summary["ok"] is True
    assert summary["mutation_case_count"] == 21
    assert summary["mutation_case_fail_count"] == 0
    assert summary["mutation_proven_format_rule_count"] == 21
    assert summary["mutation_proven_unique_rule_count"] == 16
    assert summary["formats"] == {
        "docx": {"total": 7, "passed": 7, "failed": 0},
        "pptx": {"total": 7, "passed": 7, "failed": 0},
        "xlsx": {"total": 7, "passed": 7, "failed": 0},
    }


def test_p97_coverage_map_marks_uncovered_rules(tmp_path: Path) -> None:
    summary = run_gate(tmp_path)
    counts = summary["coverage_map"]["counts"]

    assert counts["docx"]["mutation_proven"] == 7
    assert counts["pptx"]["mutation_proven"] == 7
    assert counts["xlsx"]["mutation_proven"] == 7
    assert counts["docx"]["uncovered_in_p97"] > 0
    assert counts["pptx"]["uncovered_in_p97"] > 0
    assert counts["xlsx"]["uncovered_in_p97"] > 0


def test_p97_source_state_avoids_self_commit_pointer(tmp_path: Path) -> None:
    summary = run_gate(tmp_path)

    assert "ooxml-stack" not in summary["source_heads"]
    assert {row["path"] for row in summary["generator_source_files"]} == {
        "scripts/run_p97_mutation_gate.py",
        "scripts/p97_mutation_cases.py",
    }


def test_p97_covers_main_rule_families(tmp_path: Path) -> None:
    summary = run_gate(tmp_path)
    proven = {(row["format"], row["rule_id"]) for row in summary["cases"]}

    assert {
        ("docx", "content_types_integrity"),
        ("pptx", "content_types_integrity"),
        ("xlsx", "sheet_rid_resolvable"),
        ("docx", "image_rel_integrity"),
        ("pptx", "blip_fill_integrity"),
        ("xlsx", "blip_fill_integrity"),
        ("docx", "color_no_hash"),
        ("pptx", "color_no_hash"),
        ("docx", "table_grid_consistency"),
        ("pptx", "table_grid_consistency"),
        ("xlsx", "table_grid_consistency"),
        ("docx", "body_required"),
        ("pptx", "element_order"),
        ("xlsx", "cell_ref_matches_row"),
    } <= proven


def test_p97_writes_manifest_and_summary(tmp_path: Path) -> None:
    run_gate(tmp_path)

    summary = json.loads((tmp_path / "rule-coverage-mutation-gate-summary.json").read_text())
    manifest = json.loads((tmp_path / "manifest.json").read_text())

    assert summary["schema_version"] == "p97-rule-coverage-mutation-gate-v1"
    assert manifest["schema_version"] == "p97-evidence-manifest-v1"
    assert manifest["files"][0]["path"].endswith("rule-coverage-mutation-gate-summary.json")


def test_p97_release_profile_matches_generated_summary() -> None:
    root = Path(__file__).resolve().parents[1]
    summary = json.loads((root / "release-evidence/p97/rule-coverage-mutation-gate-summary.json").read_text())
    profile = json.loads((root / "release-profiles/p97-rule-coverage-mutation.json").read_text())

    assert profile["ok"] == summary["ok"]
    assert profile["expected_metrics"]["mutation_case_count"] == summary["mutation_case_count"]
    assert profile["expected_metrics"]["mutation_case_pass_count"] == summary["mutation_case_pass_count"]
    assert profile["expected_metrics"]["mutation_case_fail_count"] == summary["mutation_case_fail_count"]
    assert profile["expected_metrics"]["mutation_proven_format_rule_count"] == summary["mutation_proven_format_rule_count"]
    assert profile["expected_metrics"]["mutation_proven_unique_rule_count"] == summary["mutation_proven_unique_rule_count"]
    assert profile["expected_metrics"]["formats"] == summary["formats"]
    assert profile["coverage_counts"] == summary["coverage_map"]["counts"]
