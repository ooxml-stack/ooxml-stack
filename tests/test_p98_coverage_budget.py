from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_p98_coverage_budget import compute_baseline, P98_PROVEN


def _registries():
    # Reuse the same import machinery as the gate for a lightweight check.
    from build_p98_coverage_budget import docx_registry, pptx_registry, shared_registry

    return {
        "docx": docx_registry(),
        "pptx": pptx_registry(),
        "xlsx": shared_registry(),
    }


def test_p98_budget_reduces_p97_uncovered_total() -> None:
    bl = compute_baseline(_registries())
    # P97 documented 76; P98-A must strictly reduce the current discovered total.
    assert bl["total_uncovered"] < 76
    for fmt in ("docx", "pptx", "xlsx"):
        assert bl["by_format"][fmt]["uncovered_count"] < {  # P97 historical per-format
            "docx": 31, "pptx": 29, "xlsx": 16,
        }[fmt]


def test_p98_budget_tracks_newly_proven_rules() -> None:
    bl = compute_baseline(_registries())
    # pptx: P97 proved 7 (or more with shared) and P98 added chartex/smartart/media.
    assert "chartex_mc_wrapper" in P98_PROVEN["pptx"]
    assert all(
        rule not in bl["by_format"]["pptx"]["uncovered_rules"]
        for rule in P98_PROVEN["pptx"]
    )


def test_p98_budget_emits_deferred_families() -> None:
    bl = compute_baseline(_registries())
    deferred_pptx = {f["family"] for f in bl["by_format"]["pptx"]["deferred_families"]}
    deferred_docx = {f["family"] for f in bl["by_format"]["docx"]["deferred_families"]}
    assert "presentation_animation" in deferred_pptx
    assert "word_drawing_geometry" in deferred_docx


def test_p98_budget_baseline_file_matches_generated(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    generated = tmp_path / "coverage-budget-baseline.json"
    # Pytest plugins can preload installed registries; verify the actual generator.
    subprocess.run(
        [sys.executable, str(root / "scripts/build_p98_coverage_budget.py"), "--out", str(generated)],
        check=True, capture_output=True, text=True,
    )
    rebuilt = json.loads(generated.read_text())
    filed = json.loads((root / "release-evidence/p98/coverage-budget-baseline.json").read_text())

    assert filed["schema_version"] == "p98-coverage-budget-v1"
    filed.pop("generated_at_utc")
    rebuilt.pop("generated_at_utc")
    assert filed == rebuilt
    assert filed["p97_historical_baseline"] == {"docx": 31, "pptx": 29, "xlsx": 16, "total": 76}
