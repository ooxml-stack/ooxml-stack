from __future__ import annotations

# P98-A mutation gate runner.
#
# Proves that representative high-risk compliance rules alarm fail-closed on
# targeted malformed packages across the four previously-uncovered complex
# families: ChartEx, SmartArt / diagram relationships, spreadsheet slicers, and
# embedded package / media relationships.
#
# Mirrors the P97 runner's structure so P97 and P98 evidence stay comparable.

import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from p98_mutation_cases import cases

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT.parent
EVIDENCE = ROOT / "release-evidence" / "p98"
PROFILE = ROOT / "release-profiles" / "p98-rule-coverage-mutation.json"

# Rule ids already proven by P97; P98 rows only add NEW uncovered rules.
P97_PROVEN_RULES = frozenset({
    "content_types_integrity", "image_rel_integrity", "color_no_hash",
    "table_grid_consistency", "wml_table_grid_consistency", "numbering_ref_valid",
    "body_required", "slide_rel_completeness", "blip_fill_integrity",
    "element_order", "animation_target_ref", "sheet_rid_resolvable",
    "rel_id_unique", "styles_rgb_argb_width", "sst_count_consistent",
    "cell_ref_matches_row",
})


def add_path(path: Path) -> None:
    raw = str(path)
    sys.path = [item for item in sys.path if item != raw]
    sys.path.insert(0, raw)


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


def xlsx_registry():
    return shared_registry()


def write_zip(path: Path, files: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def run_registry(registry: Any, path: Path) -> list[dict[str, Any]]:
    rows = []
    for finding in registry.run(path):
        rows.append({
            "rule_id": finding.rule_id,
            "severity": finding.severity.value,
            "message": finding.message,
            "file_path": finding.file_path,
        })
    return rows


def case_result(case: dict[str, Any], temp: Path, registry_map: dict[str, Any]) -> dict[str, Any]:
    registry = registry_map[case["format"]]
    control = temp / f"{case['id']}-control.{case['format']}"
    mutant = temp / f"{case['id']}-mutant.{case['format']}"
    write_zip(control, case["control"])
    write_zip(mutant, case["mutant"])
    control_findings = run_registry(registry, control)
    mutant_findings = run_registry(registry, mutant)
    rule_id = case["rule_id"]
    control_hit = any(row["rule_id"] == rule_id for row in control_findings)
    mutant_hit = any(row["rule_id"] == rule_id for row in mutant_findings)
    return {
        "id": case["id"],
        "format": case["format"],
        "rule_id": rule_id,
        "rule_family": case["rule_family"],
        "status": "passed" if mutant_hit and not control_hit else "failed",
        "control_expected_rule_hit": control_hit,
        "mutant_expected_rule_hit": mutant_hit,
        "control_finding_count": len(control_findings),
        "mutant_finding_count": len(mutant_findings),
        "mutant_findings": mutant_findings,
    }


def rule_matrix(registries: dict[str, Any], proven: set[tuple[str, str]]) -> dict[str, Any]:
    all_rules = sorted({rule.id for registry in registries.values() for rule in registry.rules})
    by_format = {}
    counts = {fmt: {} for fmt in registries}
    for fmt, registry in registries.items():
        tagged = {rule.id for rule in registry.rules if fmt in rule.tags}
        by_format[fmt] = {}
        for rule_id in all_rules:
            status = coverage_status(fmt, rule_id, tagged, proven)
            by_format[fmt][rule_id] = status
            counts[fmt][status] = counts[fmt].get(status, 0) + 1
    return {"rules": all_rules, "by_format": by_format, "counts": counts}


def coverage_status(fmt: str, rule_id: str, tagged: set[str], proven: set[tuple[str, str]]) -> str:
    if rule_id not in tagged:
        return "not_applicable_to_format"
    if (fmt, rule_id) in proven:
        return "mutation_proven"
    return "uncovered_in_p98"


def git_head(path: Path) -> str:
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "--short=8", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def source_heads() -> dict[str, str]:
    repos = ("ooxml-test-framework", "python-docx", "python-pptx", "python-xlsx")
    return {repo: git_head(PROJECTS / repo) for repo in repos}


def build_summary(results: list[dict[str, Any]], registries: dict[str, Any]) -> dict[str, Any]:
    proven = {(row["format"], row["rule_id"]) for row in results if row["status"] == "passed"}
    unique_rules = {rule_id for _, rule_id in proven}
    matrix = rule_matrix(registries, proven)
    failed = [row for row in results if row["status"] != "passed"]
    return {
        "schema_version": "p98-rule-coverage-mutation-gate-v1",
        "phase": "P98-A",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "claim": (
            "P98-A mutation gate passed for representative high-risk uncovered "
            "families (ChartEx, SmartArt/diagram, spreadsheet slicer, embedded "
            "package/media); remaining uncovered rules are mapped, not claimed complete."
        ),
        "ok": not failed,
        "mutation_case_count": len(results),
        "mutation_case_pass_count": len(results) - len(failed),
        "mutation_case_fail_count": len(failed),
        "mutation_proven_format_rule_count": len(proven),
        "mutation_proven_unique_rule_count": len(unique_rules),
        "formats": format_counts(results),
        "cases": results,
        "coverage_map": matrix,
        "source_heads": source_heads(),
        "generator_source_files": generator_source_files(),
        "boundaries": [
            "P98 does not claim complete mutation coverage for every registered rule.",
            "P98 proves representative alarm paths in four previously-uncovered complex families.",
            "No native Office replay was run in this phase; P98-B is separate Office evidence.",
            "ooxml-stack self commit is not stored in source_heads because evidence files change the commit hash.",
        ],
    }


def generator_source_files() -> list[dict[str, Any]]:
    return [
        manifest_file(ROOT / "scripts" / "run_p98_mutation_gate.py"),
        manifest_file(ROOT / "scripts" / "p98_mutation_cases.py"),
    ]


def format_counts(results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for row in results:
        bucket = counts.setdefault(row["format"], {"total": 0, "passed": 0, "failed": 0})
        bucket["total"] += 1
        bucket["passed" if row["status"] == "passed" else "failed"] += 1
    return counts


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_file(path: Path) -> dict[str, Any]:
    try:
        rel_path = path.relative_to(ROOT)
    except ValueError:
        rel_path = Path(path.name)
    return {
        "path": str(rel_path),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
    }


def write_outputs(summary: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "rule-coverage-mutation-gate-summary.json"
    summary_path.write_text(json.dumps(summary, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "p98-evidence-manifest-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "files": [manifest_file(summary_path)],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def run_gate(out_dir: Path = EVIDENCE) -> dict[str, Any]:
    current_registries = registries()
    with tempfile.TemporaryDirectory(prefix="p98-mutation-") as tmp:
        results = [case_result(case, Path(tmp), current_registries) for case in cases()]
    summary = build_summary(results, current_registries)
    write_outputs(summary, out_dir)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    summary = run_gate(args.out_dir)
    print(json.dumps({
        "ok": summary["ok"],
        "mutation_case_count": summary["mutation_case_count"],
        "mutation_case_pass_count": summary["mutation_case_pass_count"],
        "mutation_proven_format_rule_count": summary["mutation_proven_format_rule_count"],
        "mutation_proven_unique_rule_count": summary["mutation_proven_unique_rule_count"],
        "formats": summary["formats"],
    }, indent=2))
    return 0 if summary["ok"] else 1


def registries() -> dict[str, Any]:
    return {"docx": docx_registry(), "pptx": pptx_registry(), "xlsx": xlsx_registry()}


if __name__ == "__main__":
    raise SystemExit(main())