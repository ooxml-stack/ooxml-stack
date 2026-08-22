from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_semantic_editability_high_yield_candidates import build_ranking


def _row(package: str, index: int, part: str = "ppt/slides/slide1.xml") -> dict[str, str]:
    return {
        "family": "office_extension",
        "format": "pptx",
        "operation_hydration_status": "hydrated",
        "operation_id": "office_extension.known_metadata.set_value",
        "package_id": package,
        "part_name": part,
        "qname": "{urn:test}node",
        "row_id": f"pptx|{package}|{part}|stable-{index}",
        "source_row_id": f"source-{package}-{index}",
    }


def _runner(rows: list[dict]) -> dict[str, int]:
    schema_blocked = [row for row in rows if row.get("schema_blocked")]
    planned = len(rows) - len(schema_blocked)
    return {"planned_safe_rows": planned, "runner_schema_policy_skipped_rows": len(schema_blocked)}


def test_ranking_reports_promotion_ready_bucket() -> None:
    ranking = build_ranking([_row("pkg-a", 1)], {}, runner_planner=_runner)

    bucket = ranking["top_buckets"][0]

    assert bucket["classification"] == "promotion_ready"
    assert bucket["safe_planned_rows"] == 1


def test_ranking_reports_office_boundary_only_bucket() -> None:
    ranking = build_ranking([_row("pkg-a", 1)], {"known_boundary_packages": [{"package_id": "pkg-a"}]}, runner_planner=_runner)

    bucket = ranking["answers"]["office_boundary_only"][0]

    assert bucket["classification"] == "office_boundary_only"
    assert bucket["boundary_included_planned_rows"] == 1
    assert bucket["normal_skip_counts"] == {"known_office_boundary": 1}


def test_ranking_reports_schema_policy_blocked_bucket() -> None:
    row = _row("pkg-a", 1) | {"schema_blocked": True}

    ranking = build_ranking([row], {}, runner_planner=_runner)

    bucket = ranking["answers"]["schema_policy_blocked"][0]

    assert bucket["classification"] == "schema_policy_blocked"
    assert bucket["potential_row_gain"] == 1


def test_ranking_reports_public_path_blocked_bucket() -> None:
    row = _row("pkg-a", 1, part="customXml/item1.xml")

    ranking = build_ranking([row], {}, runner_planner=_runner)

    bucket = ranking["answers"]["public_path_blocked"][0]

    assert bucket["classification"] == "public_path_blocked"
    assert bucket["boundary_included_skip_counts"] == {"public_path_unsupported_part": 1}
