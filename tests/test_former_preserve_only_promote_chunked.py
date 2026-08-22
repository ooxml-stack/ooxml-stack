from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import former_preserve_only_promote_chunked as chunked
from former_preserve_only_chunk_evidence import timing_markdown, timing_summary


def test_plans_for_chunk_fails_on_row_membership_drift(monkeypatch) -> None:
    chunk = _chunk(planned=2)
    rows = {f"row-{index}": _row(index) for index in range(2)}
    monkeypatch.setattr(chunked.promote, "_plans", lambda rows, args: [{"row": rows[0]}])

    with pytest.raises(ValueError, match="exact row_id membership"):
        chunked._plans_for_chunk(chunk, ["row-0", "row-1"], rows, _args())


def test_plans_for_chunk_fails_on_row_ids_hash_drift() -> None:
    chunk = _chunk(planned=1)
    rows = {"row-9": _row(9)}

    with pytest.raises(ValueError, match="row_ids_hash"):
        chunked._plans_for_chunk(chunk, ["row-9"], rows, _args())


def test_run_chunk_merges_only_after_staged_hard_audit(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    chunk = _chunk()
    row = _row(0)
    _patch_replay(monkeypatch, tmp_path, row)
    monkeypatch.setattr(chunked, "_write_staged", lambda chunk, rows: calls.append("staged"))
    monkeypatch.setattr(chunked, "audit_rows", lambda rows, expected_count: calls.append("audit") or {"audit_pass": True})
    monkeypatch.setattr(chunked, "_merge_rows", lambda rows, label: calls.append("merge"))

    record = chunked.run_chunk(chunk, ["row-0"], {"row-0": row}, _args(run_office=True))

    assert record["status"] == "promoted"
    assert calls == ["staged", "audit", "merge"]


def test_run_chunk_stages_goal_evidence_fields(monkeypatch, tmp_path) -> None:
    staged: list[dict] = []
    chunk = _chunk()
    row = _row(0)
    _patch_replay(monkeypatch, tmp_path, row)
    monkeypatch.setattr(chunked, "_write_staged", lambda chunk, rows: staged.extend(rows))
    monkeypatch.setattr(chunked, "audit_rows", lambda rows, expected_count: {"audit_pass": True})
    monkeypatch.setattr(chunked, "_merge_rows", lambda rows, label: None)

    record = chunked.run_chunk(chunk, ["row-0"], {"row-0": row}, _args(run_office=True))

    evidence = staged[0]
    assert record["status"] == "promoted"
    assert evidence["chunk_id"] == chunk["chunk_id"]
    assert evidence["chunk_label"].startswith("chunk-")
    assert evidence["requested_semantic_value"] == "b"
    assert evidence["target_changed"] is True
    assert evidence["exact_after_value_hit"] is True
    assert evidence["same_operation_sibling_unchanged"] is True
    assert evidence["native_office_status"] == "pass"
    assert evidence["repair_dialog_count"] == 0


def test_run_chunk_does_not_merge_when_audit_fails(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    chunk = _chunk()
    row = _row(0)
    _patch_replay(monkeypatch, tmp_path, row)
    monkeypatch.setattr(chunked, "_write_staged", lambda chunk, rows: calls.append("staged"))
    monkeypatch.setattr(chunked, "audit_rows", lambda rows, expected_count: {"audit_pass": False, "failures": {"pass": ["row-0"]}})
    monkeypatch.setattr(chunked, "_merge_rows", lambda rows, label: calls.append("merge"))

    record = chunked.run_chunk(chunk, ["row-0"], {"row-0": row}, _args(run_office=True))

    assert record["status"] == "hard_audit_failed"
    assert record["stage"] == "hard_audit"
    assert calls == ["staged"]


def test_office_boundary_is_not_promoted(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    chunk = _chunk()
    row = _row(0)
    _patch_replay(monkeypatch, tmp_path, row, office={"return_code": 1, "status": "repair_dialog"})
    monkeypatch.setattr(chunked, "_write_staged", lambda chunk, rows: calls.append("staged"))
    monkeypatch.setattr(chunked, "_write_boundary", lambda chunk, status, rows, office: calls.append(status))
    monkeypatch.setattr(chunked, "_merge_rows", lambda rows, label: calls.append("merge"))

    record = chunked.run_chunk(chunk, ["row-0"], {"row-0": row}, _args(run_office=True))

    assert record["status"] == "office_boundary"
    assert calls == ["staged", "office_boundary"]


def test_run_chunk_classifies_replay_exceptions_as_infra_failed(monkeypatch, tmp_path) -> None:
    chunk = _chunk()
    row = _row(0)
    monkeypatch.setattr(chunked.promote, "_plans", lambda rows, args: [{"row": row, "before": "a", "requested": "b"}])
    monkeypatch.setattr(chunked.promote, "_copy", lambda row, label: tmp_path / "out.pptx")
    monkeypatch.setattr(chunked.promote, "_run_api", lambda path, plans: (_ for _ in ()).throw(RuntimeError("boom")))

    record = chunked.run_chunk(chunk, ["row-0"], {"row-0": row}, _args(run_office=True))

    assert record["status"] == "infra_failed"
    assert record["stage"] == "api"


def test_guarded_timeout_records_current_stage(monkeypatch) -> None:
    chunk = _chunk()
    args = _args()
    args.chunk_timeout_seconds = 1
    monkeypatch.setattr(
        chunked,
        "run_chunk",
        lambda chunk, row_ids, rows_by_id, args, stage: (_ for _ in ()).throw(chunked.ChunkTimeout("office_gate")),
    )

    record = chunked._run_chunk_guarded(chunk, ["row-0"], {"row-0": _row(0)}, args)

    assert record["status"] == "timeout"
    assert record["stage"] == "office_gate"


def test_skip_chunk_uses_checkpoint_unless_retry_failed() -> None:
    args = argparse.Namespace(retry_failed=False)
    retry = argparse.Namespace(retry_failed=True)
    checkpoint = {"records": [{"chunk_id": "chunk-pkg-office-extension-0001", "status": "promoted"}]}

    assert chunked._skip_chunk(_chunk(), checkpoint, args) is True
    assert chunked._skip_chunk(_chunk(), checkpoint, retry) is False


def test_timing_summary_separates_run_and_cumulative_elapsed(monkeypatch) -> None:
    monkeypatch.setattr("former_preserve_only_chunk_evidence.time.monotonic", lambda: 110.0)
    current = [{"chunk_id": "chunk-new", "status": "promoted", "duration_s": 10.0}]
    cumulative = current + [{"chunk_id": "chunk-old", "status": "timeout", "duration_s": 480.0}]

    summary = timing_summary(current, cumulative, started=100.0)
    markdown = timing_markdown(summary)

    assert summary["run_elapsed_seconds"] == 10.0
    assert summary["cumulative_chunk_elapsed_seconds"] == 490.0
    assert summary["run_status_counts"] == {"promoted": 1}
    assert summary["checkpoint_status_counts"] == {"promoted": 1, "timeout": 1}
    assert "Run elapsed seconds: 10.0" in markdown
    assert "Cumulative chunk elapsed seconds: 490.0" in markdown


def _patch_replay(monkeypatch, tmp_path: Path, row: dict, office: dict | None = None) -> None:
    plans = [{"row": row, "before": "a", "requested": "b"}]
    api = {"errors": [], "new_errors": []}
    cli = {"return_code": 0}
    mcp = {"return_code": 0}
    office = office or {"return_code": 0, "status": "pass"}
    monkeypatch.setattr(chunked.promote, "_plans", lambda rows, args: plans)
    monkeypatch.setattr(chunked.promote, "_copy", lambda row, label: tmp_path / "out.pptx")
    monkeypatch.setattr(chunked.promote, "_run_api", lambda path, plans: api)
    monkeypatch.setattr(chunked.promote, "_run_cli", lambda plans, label: cli)
    monkeypatch.setattr(chunked.promote, "_run_mcp", lambda plans, label: mcp)
    monkeypatch.setattr(chunked.anyio, "run", lambda fn, plans, label: fn(plans, label))
    monkeypatch.setattr(chunked.promote, "_run_office", lambda path, enabled: office)
    monkeypatch.setattr(chunked.promote, "_evidence_row", lambda *args: _evidence(row, office))


def _chunk(planned: int = 1) -> dict:
    row_ids = [f"row-{index}" for index in range(planned)]
    return {
        "chunk_id": "chunk-pkg-office-extension-0001",
        "chunk_index": 1,
        "family": "office_extension",
        "package_id": "pkg",
        "planned_row_count": planned,
        "row_ids_hash": _hash(row_ids),
    }


def _row(index: int) -> dict[str, str]:
    return {
        "input_file": "corpus/pptx/pkg.pptx",
        "package_id": "pkg",
        "part_name": "ppt/slides/slide1.xml",
        "row_id": f"row-{index}",
    }


def _evidence(row: dict, office: dict) -> dict:
    return {
        "row_id": row["row_id"],
        "pass": office["status"] == "pass",
        "requested_semantic_change": {"value": "b"},
        "semantic_edit_pass": True,
        "cli_path_checked": True,
        "cli_output_file": "public-paths/cli.jsonl",
        "mcp_path_checked": True,
        "mcp_output_file": "public-paths/mcp.jsonl",
        "native_office_result": office["status"],
        "office_result_id": office.get("office_json", "office.json"),
        "target_semantic_changed": True,
        "sibling_unexpected_semantic_mutation_count": 0,
    }


def _args(run_office: bool = False) -> argparse.Namespace:
    return argparse.Namespace(requested_value="", run_office=run_office, label_prefix="chunk")


def _hash(row_ids: list[str]) -> str:
    return hashlib.sha256(("\n".join(row_ids) + "\n").encode()).hexdigest()
