from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_close_error_diagnostics import build_diagnostics
from build_close_error_rerun_report import build_report
import run_close_error_office_rerun
import run_close_error_exact_replay
from run_close_error_exact_replay import _build_replay_inputs, _selected_records
from run_close_error_office_rerun import _run_office_preserving_source, _select_candidates, _summary


def test_close_error_diagnostics_selects_rerunnable_rows(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence/former-preserve-only-semantic-editability"
    _write_public(evidence, "demo")
    output = evidence / "promotion-outputs/api-demo-docx_pkg.docx"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"docx")
    office = evidence / "office-results/api-demo-docx_pkg.json"
    _write_office(office, "close_error", "ooxml-stack/release-evidence/former-preserve-only-semantic-editability/promotion-outputs/api-demo-docx_pkg.docx")
    _write_checkpoint(evidence, "release-evidence/former-preserve-only-semantic-editability/office-results/api-demo-docx_pkg.json")

    summary = build_diagnostics(tmp_path)

    row = summary["records"][0]
    assert summary["close_error_office_result_count"] == 1
    assert summary["candidate_row_count"] == 2
    assert row["rerun_allowed"] is True
    assert row["diagnostic_priority"] == "high"
    assert row["output_package_hash"].startswith("sha256:")


def test_close_error_diagnostics_ignores_repair_dialog(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence/former-preserve-only-semantic-editability"
    office = evidence / "office-results/api-demo-docx_pkg.json"
    _write_office(office, "repair_dialog", "api-demo-docx_pkg.docx")

    summary = build_diagnostics(tmp_path)

    assert summary["close_error_office_result_count"] == 0
    assert summary["records"] == []


def test_close_error_diagnostics_keeps_missing_output_as_non_rerunnable(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence/former-preserve-only-semantic-editability"
    _write_public(evidence, "demo")
    office = evidence / "office-results/api-demo-docx_pkg.json"
    _write_office(office, "close_error", "ooxml-stack/release-evidence/former-preserve-only-semantic-editability/promotion-outputs/missing.docx")
    _write_checkpoint(evidence, "release-evidence/former-preserve-only-semantic-editability/office-results/api-demo-docx_pkg.json")

    summary = build_diagnostics(tmp_path)

    row = summary["records"][0]
    assert row["rerun_allowed"] is False
    assert row["candidate_class"] == "missing_output"


def test_close_error_rerun_report_keeps_repeated_close_error_as_boundary(tmp_path: Path) -> None:
    diagnostic = tmp_path / "diagnostic.json"
    raw = tmp_path / "raw.json"
    output = "release-evidence/former-preserve-only-semantic-editability/promotion-outputs/api-demo-docx_pkg.docx"
    diagnostic.write_text(json.dumps({"records": [{"output_file": output, "package_id": "docx_pkg", "source_label": "demo", "planned_row_count": 2}]}), encoding="utf-8")
    raw.write_text(json.dumps({"results": [{"file": f"ooxml-stack/{output}", "status": "close_error", "message": "User canceled"}]}), encoding="utf-8")

    summary = build_report(tmp_path, diagnostic, raw)

    row = summary["records"][0]
    assert summary["confirmed_boundary_count"] == 1
    assert summary["recovered_promoted_row_count"] == 0
    assert row["promotion_eligible_after_rerun"] is False


def test_close_error_rerun_report_requires_exact_replay_after_pass(tmp_path: Path) -> None:
    diagnostic = tmp_path / "diagnostic.json"
    raw = tmp_path / "raw.json"
    output = "release-evidence/former-preserve-only-semantic-editability/promotion-outputs/api-demo-docx_pkg.docx"
    diagnostic.write_text(json.dumps({"records": [{"output_file": output, "package_id": "docx_pkg", "source_label": "demo"}]}), encoding="utf-8")
    raw.write_text(json.dumps({"results": [{"file": output, "status": "pass", "message": "ok"}]}), encoding="utf-8")

    summary = build_report(tmp_path, diagnostic, raw)

    assert summary["automation_transient_count"] == 1
    assert summary["recovered_promoted_row_count"] == 0
    assert summary["records"][0]["reason"].startswith("Office-only rerun passed")


def test_close_error_rerun_selection_skips_existing_raw_result() -> None:
    records = [
        _diagnostic_row("a", "out-a.docx"),
        _diagnostic_row("b", "out-b.docx"),
    ]
    raw = {"results": [{"file": "out-a.docx", "status": "close_error"}]}
    args = type("Args", (), {"limit": 5, "priority": "high", "candidate_class": "small_replay_candidate", "package_id": "", "include_existing": False})()

    selected = _select_candidates(records, raw, args)

    assert [row["package_id"] for row in selected] == ["b"]


def test_close_error_rerun_summary_counts_statuses() -> None:
    summary = _summary([{"status": "pass"}, {"status": "close_error"}, {"status": "pass_with_dialog"}])

    assert summary["total"] == 3
    assert summary["pass"] == 1
    assert summary["pass_total"] == 2
    assert summary["by_status"]["close_error"] == 1
    assert summary["gate_pass"] is False


def test_close_error_rerun_preserves_source_office_json(tmp_path: Path, monkeypatch) -> None:
    office_json = tmp_path / "office.json"
    office_json.write_text('{"original": true}', encoding="utf-8")

    def fake_office_json(_path: Path) -> Path:
        return office_json

    def fake_run_office(_path: Path, _enabled: bool) -> dict[str, object]:
        office_json.write_text('{"rerun": true}', encoding="utf-8")
        return {"status": "pass", "results": [{"status": "pass"}], "office_json": str(office_json)}

    monkeypatch.setattr(run_close_error_office_rerun, "_office_json", fake_office_json)
    monkeypatch.setattr(run_close_error_office_rerun, "_run_office", fake_run_office)

    office = _run_office_preserving_source(tmp_path / "sample.docx")

    assert office["status"] == "pass"
    assert office_json.read_text(encoding="utf-8") == '{"original": true}'


def test_close_error_exact_replay_selects_transient_records() -> None:
    args = type("Args", (), {"source_label": ["good"], "limit": 5})()
    records = [
        {"source_label": "good", "source_chunk_id": "new", "classification": "automation_transient", "promotion_eligible_after_rerun": True},
        {"source_label": "good", "source_chunk_id": "done", "classification": "automation_transient", "promotion_eligible_after_rerun": True},
        {"source_label": "bad", "classification": "automation_transient", "promotion_eligible_after_rerun": True},
        {"source_label": "good", "classification": "confirmed_boundary", "promotion_eligible_after_rerun": False},
    ]

    selected = _selected_records(records, args, {"done"})

    assert [row["source_chunk_id"] for row in selected] == ["new"]


def test_close_error_exact_replay_builds_temp_chunk_inputs(tmp_path: Path, monkeypatch) -> None:
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "chunk-a.jsonl").write_text('{"row_id":"r1"}\n{"row_id":"r2"}\n', encoding="utf-8")
    monkeypatch.setattr(run_close_error_exact_replay, "STAGED", staged)

    chunks, row_sets = _build_replay_inputs(
        [
            {
                "family": "office_extension",
                "operation_ids": ["office_extension.known_metadata.set_value"],
                "package_id": "pkg",
                "source_chunk_id": "chunk-a",
            }
        ]
    )

    assert chunks[0]["planned_row_count"] == 2
    assert row_sets == [{"chunk_id": "chunk-a", "row_ids": ["r1", "r2"]}]


def test_close_error_exact_replay_skips_handled_hash(tmp_path: Path, monkeypatch) -> None:
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "chunk-a.jsonl").write_text('{"row_id":"r1"}\n', encoding="utf-8")
    monkeypatch.setattr(run_close_error_exact_replay, "STAGED", staged)

    chunks, row_sets = _build_replay_inputs(
        [{"family": "office_extension", "operation_ids": [], "package_id": "pkg", "source_chunk_id": "chunk-a"}],
        {"fa347eb70a4d91f765ee8d48e892e3a7e07df3d4d76d1feb2a0feea19d9c83f6"},
    )

    assert chunks == []
    assert row_sets == []


def _write_public(evidence: Path, label: str) -> None:
    public = evidence / "public-paths"
    public.mkdir(parents=True)
    (public / f"cli-{label}.jsonl").write_text('{"row_id":"a"}\n{"row_id":"b"}\n', encoding="utf-8")


def _write_office(path: Path, status: str, file_name: str) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"results": [{"status": status, "file": file_name, "message": "Microsoft Word got an error: User canceled."}]}), encoding="utf-8")


def _write_checkpoint(evidence: Path, office_result: str) -> None:
    checkpoint = evidence / "chunk-promotion-checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "chunk_id": "chunk-a",
                        "family": "alternate_content",
                        "label": "demo",
                        "office_result_file": office_result,
                        "operation_ids": ["alternate_content.choice.metadata.set_value"],
                        "package_id": "docx_pkg",
                        "planned_row_count": 2,
                        "public_path_file": "public.jsonl",
                        "stage": "office_gate",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _diagnostic_row(package_id: str, output_file: str) -> dict[str, object]:
    return {
        "candidate_class": "small_replay_candidate",
        "diagnostic_priority": "high",
        "output_file": output_file,
        "package_id": package_id,
        "planned_row_count": 1,
        "rerun_allowed": True,
        "source_label": package_id,
    }
