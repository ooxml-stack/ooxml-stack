from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_semantic_editability_chunk_plan import build_plan
from former_preserve_only_promoted_index import promoted_index, row_target_key, split_alias_rows
from semantic_editability_failed_rows import failed_source_ids


def test_chunk_plan_skips_known_row_level_failures() -> None:
    row = _row("pkg-a", 1)

    plan, row_sets = build_plan(
        [row],
        _remaining(),
        set(),
        set(),
        failed_sources={row["source_row_id"]},
        chunk_size=5,
        runner_filter=False,
    )

    assert plan["selected_row_count"] == 0
    assert plan["skipped_counts"]["known_row_level_failure"] == 1
    assert row_sets == []


def test_chunk_plan_filters_by_qname() -> None:
    wanted = _row("pkg-a", 1)
    other = _row("pkg-a", 2) | {"qname": "{urn:test}other"}

    plan, row_sets = build_plan([other, wanted], _remaining(), set(), set(), chunk_size=5, qname=wanted["qname"], runner_filter=False)

    assert plan["selected_row_count"] == 1
    assert plan["skipped_counts"]["qname_filter"] == 1
    assert row_sets[0]["row_ids"] == [wanted["row_id"]]


def test_failed_source_ids_reads_staged_failure_rows(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    staged = tmp_path / "staged"
    staged.mkdir()
    checkpoint.write_text(
        '{"records":[{"chunk_id":"chunk-a","status":"public_api_failed"},{"chunk_id":"chunk-b","status":"promoted"}]}',
        encoding="utf-8",
    )
    (staged / "chunk-a.jsonl").write_text('{"source_row_id":"source-a"}\n', encoding="utf-8")
    (staged / "chunk-b.jsonl").write_text('{"source_row_id":"source-b"}\n', encoding="utf-8")

    assert failed_source_ids(checkpoint, staged) == {"source-a"}


def test_promoted_index_keeps_source_ids_for_alias_targets(tmp_path: Path) -> None:
    rows = tmp_path / "promotion-rows.jsonl"
    payload = {
        "operation_id": "vml.formula.eqn.set_value",
        "operation_params": {},
        "operation_target": "word/header.xml::/v:formulas/v:f[1]",
        "package_id": "pkg-a",
        "pass": True,
    }
    rows.write_text(
        "\n".join(
            [
                _jsonl_row(payload | {"source_row_id": "source-a"}),
                _jsonl_row(payload | {"source_row_id": "source-b"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    promoted_sources, promoted_targets = promoted_index(rows)

    assert promoted_sources == {"source-a", "source-b"}
    assert len(promoted_targets) == 1


def test_split_alias_rows_separates_duplicate_targets() -> None:
    first = _promotion_row("source-a", "row-a")
    second = _promotion_row("source-b", "row-b")

    promoted, aliases = split_alias_rows([first, second])

    assert promoted == [first]
    assert aliases[0]["row_id"] == "row-b"
    assert aliases[0]["alias_of_row_id"] == "row-a"
    assert aliases[0]["alias_of_source_row_id"] == "source-a"


def test_vml_formula_target_key_matches_payload_shape() -> None:
    row = {
        "attribute_name": "eqn",
        "operation_id": "vml.formula.eqn.set_value",
        "operation_target_selector": "/v:formulas/v:f[1]",
        "package_id": "pkg-a",
        "part_name": "word/header.xml",
    }

    assert row_target_key(row) == (
        "pkg-a",
        "vml.formula.eqn.set_value",
        "word/header.xml::/v:formulas/v:f[1]",
        "",
    )


def _row(package: str, index: int) -> dict[str, str]:
    return {
        "family": "office_extension",
        "format": "pptx",
        "input_file": f"corpus/pptx/{package}.pptx",
        "operation_hydration_status": "hydrated",
        "operation_id": "office_extension.known_metadata.set_value",
        "operation_target_selector": f"/p:sld/p:spTree/a:ext[{index}]",
        "package_id": package,
        "part_name": "ppt/slides/slide1.xml",
        "qname": "{urn:test}ext",
        "row_id": f"pptx|{package}|ppt/slides/slide1.xml|stable-{index}",
        "source_row_id": f"source-{package}-{index}",
        "stable_id": f"stable-{index}",
    }


def _jsonl_row(row: dict) -> str:
    return json.dumps(row, sort_keys=True)


def _promotion_row(source: str, row_id: str) -> dict:
    return {
        "operation_id": "vml.formula.eqn.set_value",
        "operation_params": {},
        "operation_target": "word/header.xml::/v:formulas/v:f[1]",
        "package_id": "pkg-a",
        "pass": True,
        "row_id": row_id,
        "source_row_id": source,
    }


def _remaining() -> dict:
    return {
        "candidate_packages": [{"family": "office_extension", "package_id": "pkg-a", "planned_safe_rows": 1}],
        "known_boundary_packages": [],
        "known_replay_timeout_packages": [],
        "starting_remaining_count": 1,
        "starting_semantic_editable_count": 10,
    }
