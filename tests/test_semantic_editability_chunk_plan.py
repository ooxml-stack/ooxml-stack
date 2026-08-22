from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_semantic_editability_chunk_plan import _parse_args, build_plan
from chunk_replay_status import chunk_replay_summary


def _row(package: str, index: int, family: str = "office_extension", operation: str = "office_extension.known_metadata.set_value") -> dict[str, str]:
    return {
        "family": family,
        "format": "pptx",
        "input_file": f"corpus/pptx/{package}.pptx",
        "operation_hydration_status": "hydrated",
        "operation_id": operation,
        "operation_target_selector": f"/p:sld/p:spTree/a:ext[{index}]",
        "package_id": package,
        "part_name": "ppt/slides/slide1.xml",
        "qname": "{urn:test}ext",
        "row_id": f"pptx|{package}|ppt/slides/slide1.xml|stable-{index}",
        "source_row_id": f"source-{package}-{index}",
        "stable_id": f"stable-{index}",
    }


def test_chunk_plan_binds_exact_row_ids_and_hash() -> None:
    rows = [_row("pkg-a", index) for index in range(3)]

    plan, row_sets = build_plan(rows, _remaining(), set(), set(), chunk_size=2, runner_filter=False)

    assert plan["plan_scope"] == "global_next_plan"
    assert plan["plan_filters"]["operation_id"] == ""
    assert plan["planned_chunk_count"] == 2
    assert "generated_at_utc" not in plan
    assert plan["starting_semantic_editable_count"] == 10
    assert plan["starting_remaining_count"] == 3
    assert plan["packages"][0]["planned_row_count"] == 3
    assert plan["chunk_count"] == 2
    assert row_sets[0]["row_ids"] == [rows[0]["row_id"], rows[1]["row_id"]]
    assert plan["chunks"][0]["row_ids_hash"] == _hash(row_sets[0]["row_ids"])
    assert plan["row_ids_artifact_hash"]


def test_chunk_plan_skips_boundary_and_promoted_rows() -> None:
    rows = [_row("pkg-a", 1), _row("pkg-b", 1), _row("pkg-c", 1)]
    promoted_targets = {("pkg-c", "office_extension.known_metadata.set_value", "ppt/slides/slide1.xml::/p:sld/p:spTree/a:ext[1]", "")}
    remaining = _remaining(boundary="pkg-b")

    plan, row_sets = build_plan(rows, remaining, {"source-pkg-a-1"}, promoted_targets, chunk_size=5, runner_filter=False)

    assert plan["selected_row_count"] == 0
    assert row_sets == []
    assert plan["skipped_counts"]["already_promoted"] == 2
    assert plan["skipped_counts"]["known_office_boundary"] == 1


def test_chunk_plan_skips_replay_timeouts_separately() -> None:
    rows = [_row("pkg-a", 1), _row("pkg-timeout", 1)]
    remaining = _remaining(replay_timeout="pkg-timeout")
    remaining["known_replay_timeout_packages"].append({"package_id": "pkg-timeout", "operation_id": "op-a"})

    plan, row_sets = build_plan(rows, remaining, set(), set(), chunk_size=5, runner_filter=False)

    assert plan["selected_row_count"] == 1
    assert plan["plan_scope"] == "global_next_plan"
    assert plan["known_replay_timeout_package_count"] == 1
    assert plan["known_replay_timeout_entry_count"] == 2
    assert plan["known_replay_timeout_package_scope_count"] == 1
    assert plan["known_replay_timeout_operation_scope_count"] == 1
    assert plan["skipped_counts"]["known_replay_timeout"] == 1
    assert "known_office_boundary" not in plan["skipped_counts"]
    assert row_sets[0]["row_ids"] == [rows[0]["row_id"]]


def test_chunk_plan_allows_small_canary_replay_timeout_package() -> None:
    rows = [_row("pkg-timeout", 1)]
    remaining = _remaining(replay_timeout="pkg-timeout")
    remaining["known_replay_timeout_packages"][0]["family"] = "office_extension"
    remaining["known_replay_timeout_packages"][0]["operation_id"] = "office_extension.known_metadata.set_value"
    remaining["known_replay_timeout_packages"][0]["slow_replay_state"] = "small_chunk_canary_passed"

    plan, row_sets = build_plan(rows, remaining, set(), set(), chunk_size=5, runner_filter=False)

    assert plan["selected_row_count"] == 1
    assert "known_replay_timeout" not in plan["skipped_counts"]
    assert row_sets[0]["row_ids"] == [rows[0]["row_id"]]


def test_chunk_plan_allows_exact_replay_timeout_canary() -> None:
    rows = [_row("pkg-timeout", 1), _row("pkg-other", 1)]
    remaining = _remaining(replay_timeout="pkg-timeout", candidates=("pkg-timeout", "pkg-other"))
    remaining["known_replay_timeout_packages"].append({"package_id": "pkg-other", "family": "office_extension"})

    plan, row_sets = build_plan(
        rows,
        remaining,
        set(),
        set(),
        chunk_size=5,
        package_id="pkg-timeout",
        family="office_extension",
        operation_id="office_extension.known_metadata.set_value",
        include_replay_timeout_canary=True,
        runner_filter=False,
    )

    assert plan["selected_row_count"] == 1
    assert plan["plan_scope"] == "exact_replan"
    assert plan["plan_filters"]["package_id"] == "pkg-timeout"
    assert plan["plan_filters"]["family"] == "office_extension"
    assert plan["plan_filters"]["operation_id"] == "office_extension.known_metadata.set_value"
    assert plan["skipped_counts"]["known_replay_timeout"] == 1
    assert row_sets[0]["row_ids"] == [rows[0]["row_id"]]


def test_chunk_plan_exact_canary_keeps_office_boundary_skipped() -> None:
    rows = [_row("pkg-timeout", 1)]
    remaining = _remaining(boundary="pkg-timeout", replay_timeout="pkg-timeout", candidates=("pkg-timeout",))

    plan, row_sets = build_plan(
        rows,
        remaining,
        set(),
        set(),
        chunk_size=5,
        package_id="pkg-timeout",
        family="office_extension",
        operation_id="office_extension.known_metadata.set_value",
        include_replay_timeout_canary=True,
        runner_filter=False,
    )

    assert plan["selected_row_count"] == 0
    assert plan["skipped_counts"]["known_office_boundary"] == 1
    assert row_sets == []


def test_chunk_plan_canary_option_requires_exact_scope() -> None:
    try:
        _parse_args(["--include-replay-timeout-canary", "--package-id", "pkg-a", "--family", "office_extension"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected parser error")


def test_chunk_plan_keeps_other_family_replay_timeout_skipped() -> None:
    rows = [_row("pkg-timeout", 1, family="alternate_content")]
    remaining = _remaining(replay_timeout="pkg-timeout")
    remaining["known_replay_timeout_packages"][0]["family"] = "office_extension"
    remaining["known_replay_timeout_packages"][0]["operation_id"] = "office_extension.known_metadata.set_value"
    remaining["known_replay_timeout_packages"][0]["slow_replay_state"] = "small_chunk_canary_passed"

    plan, row_sets = build_plan(rows, remaining, set(), set(), chunk_size=5, runner_filter=False)

    assert plan["selected_row_count"] == 0
    assert plan["skipped_counts"]["known_replay_timeout"] == 1
    assert row_sets == []


def test_chunk_plan_exact_canary_keeps_other_operation_skipped() -> None:
    rows = [
        _row("pkg-timeout", 1, operation="office_extension.known_metadata.set_value"),
        _row("pkg-timeout", 2, operation="office_extension.other_metadata.set_value"),
    ]
    remaining = _remaining(replay_timeout="pkg-timeout", candidates=("pkg-timeout",))

    plan, row_sets = build_plan(
        rows,
        remaining,
        set(),
        set(),
        chunk_size=5,
        package_id="pkg-timeout",
        family="office_extension",
        operation_id="office_extension.known_metadata.set_value",
        include_replay_timeout_canary=True,
        runner_filter=False,
    )

    assert plan["selected_row_count"] == 1
    assert plan["skipped_counts"]["known_replay_timeout"] == 1
    assert row_sets[0]["row_ids"] == [rows[0]["row_id"]]


def test_chunk_plan_respects_package_limit_after_candidate_order() -> None:
    rows = [_row("pkg-b", 1), _row("pkg-a", 1), _row("pkg-a", 2)]
    remaining = _remaining(candidates=("pkg-a", "pkg-b"))

    plan, row_sets = build_plan(rows, remaining, set(), set(), chunk_size=10, package_limit=1, runner_filter=False)

    assert plan["selected_package_count"] == 1
    assert plan["chunks"][0]["package_id"] == "pkg-a"
    assert row_sets[0]["row_ids"] == [rows[1]["row_id"], rows[2]["row_id"]]


def test_chunk_plan_preserves_candidate_order_without_package_limit() -> None:
    rows = [_row("pkg-b", 1), _row("pkg-a", 1)]
    remaining = _remaining(candidates=("pkg-a", "pkg-b"))

    plan, _ = build_plan(rows, remaining, set(), set(), chunk_size=10, runner_filter=False)

    assert [chunk["package_id"] for chunk in plan["chunks"]] == ["pkg-a", "pkg-b"]


def test_runner_filter_removes_rows_skipped_by_hydrated_planner(monkeypatch) -> None:
    rows = [_row("pkg-a", 1), _row("pkg-a", 2), _row("pkg-b", 1)]
    monkeypatch.setattr(
        "build_semantic_editability_chunk_plan.promote._plans",
        lambda rows, args: [] if args.package_id == "pkg-a" else [{"row": rows[0]}],
    )

    plan, row_sets = build_plan(rows, _remaining(candidates=("pkg-a", "pkg-b")), set(), set(), chunk_size=10, package_limit=1)

    assert plan["selected_row_count"] == 1
    assert plan["chunks"][0]["package_id"] == "pkg-b"
    assert plan["skipped_counts"]["runner_policy_or_overlap"] == 2
    assert row_sets[0]["row_ids"] == [rows[2]["row_id"]]


def test_chunk_plan_skips_parts_without_public_path_support() -> None:
    rows = [_row("pkg-a", 1), _row("pkg-a", 2), _row("pkg-a", 3)]
    rows[0]["part_name"] = "docMetadata/LabelInfo.xml"
    rows[1]["part_name"] = "customXml/item1.xml"

    plan, row_sets = build_plan(rows, _remaining(), set(), set(), chunk_size=10, runner_filter=False)

    assert plan["selected_row_count"] == 1
    assert plan["skipped_counts"]["public_path_unsupported_part"] == 2
    assert row_sets[0]["row_ids"] == [rows[2]["row_id"]]


def test_chunk_plan_supports_format_and_size_filters() -> None:
    rows = [_row("pkg-a", 1), _row("pkg-a", 2), _row("pkg-a", 3)]
    rows[0]["format"] = "docx"

    plan, row_sets = build_plan(
        rows, _remaining(), set(), set(), chunk_size=10, fmt="pptx", max_package_mb=1.0, runner_filter=False
    )

    assert plan["selected_row_count"] == 2
    assert plan["skipped_counts"]["format_filter"] == 1
    assert row_sets[0]["row_ids"] == [rows[1]["row_id"], rows[2]["row_id"]]


def test_chunk_status_separates_current_plan_and_superseded_failures() -> None:
    checkpoint = {
        "records": [
            {"chunk_id": "current-a", "status": "promoted", "promoted_row_count": 2},
            {"chunk_id": "old-a", "status": "public_api_failed"},
            {"chunk_id": "old-b", "status": "planned_row_mismatch"},
        ]
    }
    plan = {"chunks": [{"chunk_id": "current-a"}, {"chunk_id": "current-b"}], "packages": []}

    summary = chunk_replay_summary({}, checkpoint, plan, {})

    assert summary["status_counts"] == {"planned_row_mismatch": 1, "promoted": 1, "public_api_failed": 1}
    assert summary["current_plan_status_counts"] == {"promoted": 1}
    assert summary["current_plan_failure_count"] == 0
    assert summary["current_plan_pending_chunk_count"] == 1
    assert summary["legacy_or_superseded_failure_counts"] == {"planned_row_mismatch": 1, "public_api_failed": 1}


def test_chunk_status_counts_slow_replay_promotions() -> None:
    checkpoint = {
        "records": [
            {"chunk_id": "a", "label": "canary-0001", "status": "promoted", "promoted_row_count": 5},
            {"chunk_id": "b", "label": "chunk-0002", "status": "promoted", "promoted_row_count": 7},
        ]
    }

    summary = chunk_replay_summary({}, checkpoint, {"chunks": [], "packages": []}, {})

    assert summary["slow_replay_promoted_chunk_count"] == 1
    assert summary["slow_replay_promoted_row_count"] == 5


def _remaining(boundary: str = "", candidates: tuple[str, ...] = ("pkg-a",), replay_timeout: str = "") -> dict:
    return {
        "starting_semantic_editable_count": 10,
        "starting_remaining_count": 3,
        "candidate_packages": [
            {"package_id": package, "family": "office_extension", "planned_safe_rows": 3, "total_remaining_rows": 3}
            for package in candidates
        ],
        "known_boundary_packages": [{"package_id": boundary, "status": "repair_dialog"}] if boundary else [],
        "known_replay_timeout_packages": [{"package_id": replay_timeout, "status": "replay_timeout"}]
        if replay_timeout
        else [],
    }


def _hash(row_ids: list[str]) -> str:
    return hashlib.sha256(("\n".join(row_ids) + "\n").encode()).hexdigest()
