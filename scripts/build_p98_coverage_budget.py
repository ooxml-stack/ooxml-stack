"""P98-C: mutation-coverage budget.

Builds a tracked baseline of rules not yet proven by any mutation gate
(P97 or P98-A), per registered format. Each follow-up phase must reduce this
uncovered count or explicitly defer a rule family with a reason.

The P97 phase-documented baseline was 76 uncovered rules (docx 31, pptx 29,
xlsx 16). This tool recomputes the uncovered set against the live rule
registries so the budget stays runnable and current; the P97 historical counts
are preserved for continuity.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT.parent

# Rules proven by P97's mutation gate.
P97_PROVEN = frozenset({
    "content_types_integrity", "image_rel_integrity", "color_no_hash",
    "table_grid_consistency", "wml_table_grid_consistency", "numbering_ref_valid",
    "body_required", "slide_rel_completeness", "blip_fill_integrity",
    "element_order", "animation_target_ref", "sheet_rid_resolvable",
    "rel_id_unique", "styles_rgb_argb_width", "sst_count_consistent",
    "cell_ref_matches_row",
})

# Rules proven by P98-A's mutation, keyed by tested format.
P98_PROVEN = {
    "docx": {"chartex_style_id", "document_rels_required", "header_footer_rel_valid",
             "hyperlink_rel_valid"},
    "pptx": {"chartex_mc_wrapper", "chartex_strdim_order", "chartex_style_id",
             "smartart_drawing_part", "media_rel_integrity", "chart_embedded_xlsx"},
    "xlsx": {"workbook_slicer_cache_structure", "slicer_part_contract",
             "slicer_cache_definition_consistency"},
}

# Families explicitly deferred from this phase's coverage target, with reasons.
DEFERRED_FAMILIES = {
    "docx": [
        {
            "family": "word_drawing_geometry",
            "rules": ["anchor_extent_positive", "bodypr_required",
                      "docpr_id_unique", "prsttxwarp_avlst", "sppr_child_order"],
            "reason": "mentor-preserve-only drawing shape fixtures are not yet promoted "
                      "into the negative-mutation corpus; needs a dedicated P99 extension.",
        },
    ],
    "pptx": [
        {
            "family": "presentation_animation",
            "rules": ["animation_no_grpid", "timing_structure"],
            "reason": "animation timing graphs need realistic trigger/timing parts; "
                      "assigned to a dedicated follow-up phase.",
        },
    ],
}


def add_path(path: Path) -> None:
    sys.path.insert(0, str(path))


def clear_tests_modules() -> None:
    for name in list(sys.modules):
        if name == "tests" or name.startswith("tests."):
            del sys.modules[name]


def shared_registry():
    add_path(PROJECTS / "ooxml-test-framework" / "src")
    from ooxml_testing.rules.shared import registry

    return registry


def docx_registry():
    clear_tests_modules()
    add_path(PROJECTS / "ooxml-test-framework" / "src")
    add_path(PROJECTS / "python-docx")
    from tests.compliance.docx_rules import get_combined_registry

    return get_combined_registry()


def pptx_registry():
    clear_tests_modules()
    add_path(PROJECTS / "ooxml-test-framework" / "src")
    add_path(PROJECTS / "python-pptx")
    from tests.framework.ooxml_rules.pptx_rules import get_combined_registry

    return get_combined_registry()


def compute_baseline(registries: dict[str, Any]) -> dict[str, Any]:
    baseline: dict[str, dict[str, Any]] = {}
    total = 0
    for fmt, registry in registries.items():
        tagged = {rule.id for rule in registry.rules if fmt in rule.tags}
        proven = ({r for r in P97_PROVEN if r in tagged} | P98_PROVEN.get(fmt, set()))
        uncovered = sorted(tagged - proven)
        deferred = []
        for family in DEFERRED_FAMILIES.get(fmt, []):
            deferred_rules = [r for r in family["rules"] if r in uncovered]
            if deferred_rules:
                deferred.append({"family": family["family"], "rules": deferred_rules,
                                 "reason": family["reason"]})
        baseline[fmt] = {
            "tagged_rule_count": len(tagged),
            "mutation_proven_count": len(proven),
            "uncovered_count": len(uncovered),
            "uncovered_rules": uncovered,
            "deferred_families": deferred,
        }
        total += len(uncovered)
    return {"total_uncovered": total, "by_format": baseline}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path,
                        default=ROOT / "release-evidence" / "p98" / "coverage-budget-baseline.json")
    args = parser.parse_args()

    registries = {"docx": docx_registry(), "pptx": pptx_registry(), "xlsx": shared_registry()}
    bl = compute_baseline(registries)
    doc = {
        "schema_version": "p98-coverage-budget-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "description": (
            "Tracked mutation-coverage budget. The P97 phase documented 76 uncovered "
            "rules (docx 31, pptx 29, xlsx 16). P98-A proved 12 new format-rule pairs. "
            "This baseline is recomputed against the live registry so follow-ups can "
            "run it; the counts below are registry-current, not a restatement of the "
            "P97 historical number."
        ),
        "p97_historical_baseline": {"docx": 31, "pptx": 29, "xlsx": 16, "total": 76},
        "p98_proven_additions": {fmt: sorted(rules) for fmt, rules in P98_PROVEN.items()},
        "total_uncovered": bl["total_uncovered"],
        "by_format": bl["by_format"],
        "budget_rule": (
            "Each follow-up phase must reduce total_uncovered in this baseline or "
            "explicitly defer a family with a reason; no new broad compatibility "
            "claim may exceed what the mutation evidence supports."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "total_uncovered": bl["total_uncovered"],
        "by_format": {k: v["uncovered_count"] for k, v in bl["by_format"].items()},
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())