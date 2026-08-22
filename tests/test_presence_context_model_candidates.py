from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_presence_context_model_candidates import build_candidates


def test_presence_context_candidates_rank_anchorlock_only() -> None:
    summary = build_candidates(
        {
            "schema_version": "no-semantic-field-discovery-v1",
            "groups": [
                _group("{urn:schemas-microsoft-com:office:word}anchorlock", 113, "legacy_office_drawing"),
                _group("{urn:schemas-microsoft-com:vml}formulas", 19, "vml_drawing"),
                _group("{urn:schemas-microsoft-com:vml}stroke", 5, "vml_drawing"),
            ],
        }
    )

    by_qname = {row["qname"]: row for row in summary["candidates"]}

    assert summary["candidate_count"] == 1
    assert summary["expected_canary_row_count"] == 5
    assert by_qname["{urn:schemas-microsoft-com:office:word}anchorlock"]["recommended_action"] == "design_presence_canary"
    assert by_qname["{urn:schemas-microsoft-com:vml}formulas"]["recommended_action"] == "keep_unsupported"
    assert by_qname["{urn:schemas-microsoft-com:vml}stroke"]["recommended_action"] == "needs_reference_oracle"


def test_presence_context_candidates_skip_mixed_classification() -> None:
    summary = build_candidates(
        {
            "groups": [
                {
                    "family": "legacy_office_drawing",
                    "qname": "{urn:schemas-microsoft-com:office:word}anchorlock",
                    "count": 2,
                    "recommended_action": "investigate_context_model",
                    "classification_counts": {"context_only_structural_container": 1, "empty_structural_container": 1},
                }
            ]
        }
    )

    row = summary["candidates"][0]

    assert summary["candidate_count"] == 0
    assert row["recommended_action"] == "keep_unsupported"


def _group(qname: str, count: int, family: str) -> dict:
    return {
        "family": family,
        "qname": qname,
        "count": count,
        "recommended_action": "investigate_context_model",
        "classification_counts": {"context_only_structural_container": count},
        "sample_rows": [{"row_id": "sample"}],
    }
