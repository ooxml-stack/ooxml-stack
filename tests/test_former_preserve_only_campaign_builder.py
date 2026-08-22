from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_former_preserve_only_semantic_campaign as campaign


def test_main_does_not_write_live_repo_status(tmp_path: Path, monkeypatch) -> None:
    summary = {
        "former_preserve_only_denominator": 1,
        "semantic_editable_count": 1,
        "semantic_editable_remaining": 0,
        "remaining_by_blocker": {},
        "remaining_by_family": {},
        "remaining_by_qname_top20": {},
        "anti_false_pass_gate": True,
        "full_semantic_claim_proven": False,
        "object_level_gap_rows_materialized": True,
    }

    monkeypatch.setattr(campaign, "build_campaign", lambda: ({"classification_counts": {}}, [], summary))
    monkeypatch.setattr(sys, "argv", ["prog", "--out", str(tmp_path)])

    campaign.main()

    assert not (tmp_path / "repo-status.json").exists()
    assert (tmp_path / "gap-summary.json").exists()
