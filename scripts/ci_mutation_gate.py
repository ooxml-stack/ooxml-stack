"""CI mutation gate — runs only cases for the specified format.

Usage: python3 scripts/ci_mutation_gate.py pptx|docx|xlsx

Expects the CI directory layout:
  ../python-<fmt>/     ← the current repo checkout (already on sys.path from CI)
  ooxml-test-framework ← installed via uv sync (importable as package)

Only ooxml-stack itself needs to be cloned by CI.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def registry_for(fmt: str) -> Any:
    from ooxml_testing.rules.shared import registry

    if fmt == "xlsx":
        return registry

    # pptx/docx: import format-specific rules from the sibling repo's tests/
    if fmt == "pptx":
        from tests.framework.ooxml_rules.pptx_rules import get_combined_registry
        return get_combined_registry()
    if fmt == "docx":
        from tests.compliance.docx_rules import get_combined_registry
        return get_combined_registry()
    raise ValueError(f"unsupported format: {fmt}")


def write_zip(path: Path, files: dict[str, str | bytes]) -> None:
    import zipfile
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


def case_result(case: dict[str, Any], temp: Path, registry: Any) -> dict[str, Any]:
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
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python3 scripts/ci_mutation_gate.py pptx|docx|xlsx", file=sys.stderr)
        sys.exit(2)

    fmt = sys.argv[1]
    sys.path.insert(0, str(ROOT.parent / f"python-{fmt}"))
    sys.path.insert(0, str(ROOT / "scripts"))

    from p97_mutation_cases import cases as p97_cases
    from p98_mutation_cases import cases as p98_cases

    all_cases = [c for c in p97_cases() + p98_cases() if c["format"] == fmt]
    if not all_cases:
        print(f"no mutation cases for format {fmt}", file=sys.stderr)
        sys.exit(1)

    registry = registry_for(fmt)

    passed = 0
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)
        for case in all_cases:
            result = case_result(case, temp, registry)
            if result["status"] == "passed":
                passed += 1
            else:
                failed += 1
                print(f"FAIL: {result['id']} ({result['rule_id']}): "
                      f"mutant_hit={result['mutant_expected_rule_hit']} "
                      f"control_hit={result['control_expected_rule_hit']}")

    print(f"\n{fmt}: {passed}/{passed + failed} mutation cases passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()