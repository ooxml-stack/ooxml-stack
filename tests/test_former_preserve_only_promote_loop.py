from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_promote_loop import active_office_runners
from former_preserve_only_promote_loop import audit_rows
from former_preserve_only_promote_loop import batch_summary
from former_preserve_only_promote_loop import Candidate
from former_preserve_only_promote_loop import checkpoint_packages
from former_preserve_only_promote_loop import evidence_text
from former_preserve_only_promote_loop import label_exists
from former_preserve_only_promote_loop import next_label
from former_preserve_only_promote_loop import parse_args
from former_preserve_only_promote_loop import read_checkpoint
from former_preserve_only_promote_loop import row_has_label
from former_preserve_only_promote_loop import run_candidates
from former_preserve_only_promote_loop import slug_package
from former_preserve_only_promote_loop import update_checkpoint


def complete_row(label: str) -> dict:
    return {
        "row_id": "row-1",
        "stable_id": "stable-1",
        "package_id": "pkg",
        "part_name": "ppt/slides/slide1.xml",
        "selector": "/p:sld",
        "qname": "{urn:test}tag",
        "family": "office_extension",
        "operation_id": "office_extension.known_metadata.set_value",
        "before_semantic_value": {"value": "before"},
        "after_semantic_value": {"value": "after"},
        "public_api_path": "JsonRpcServer.ooxml_apply + CLI ooxml-engine apply + MCP ooxml_apply",
        "pass": True,
        "semantic_edit_pass": True,
        "cli_path_checked": True,
        "cli_return_code": 0,
        "mcp_path_checked": True,
        "mcp_return_code": 0,
        "mcp_list_tools_pass": True,
        "mcp_call_tool_replay_pass": True,
        "native_office_result": "pass",
        "stable_id_scope": "package-local",
        "sibling_unexpected_semantic_mutation_count": 0,
        "target_semantic_changed": True,
        "package_invariant_pass": True,
        "office_result_id": f"release-evidence/office-results/api-{label}-pkg.json",
    }


def test_slug_package_shortens_ms_expansion_prefix() -> None:
    assert slug_package("pptx_ms_expansion_095_p2-05") == "pptx095-p2-05"


def test_next_label_skips_existing_batches() -> None:
    used = {"ledger-officeext-pptx095-p2-05-b1", "ledger-officeext-pptx095-p2-05-b2"}
    label = next_label("pptx_ms_expansion_095_p2-05", "ledger-officeext", used)
    assert label == "ledger-officeext-pptx095-p2-05-b3"


def test_label_exists_uses_exact_tool_tokens() -> None:
    evidence = "api-ledger-officeext-pkg-b20-pkg.json\ncli-ledger-officeext-pkg-b20.jsonl"
    assert label_exists("ledger-officeext-pkg-b20", evidence)
    assert not label_exists("ledger-officeext-pkg-b2", evidence)


def test_evidence_text_includes_promotion_outputs(monkeypatch, tmp_path) -> None:
    out = tmp_path / "campaign"
    rows = out / "promotion-rows.jsonl"
    for name in ("office-results", "public-paths", "promotion-outputs"):
        (out / name).mkdir(parents=True)
    rows.write_text("", encoding="utf-8")
    (out / "promotion-outputs" / "api-ledger-officeext-pkg-b1-demo.pptx").write_text("")
    monkeypatch.setattr("former_preserve_only_promote_loop.OUT", out)
    monkeypatch.setattr("former_preserve_only_promote_loop.ROWS", rows)

    assert "api-ledger-officeext-pkg-b1-demo.pptx" in evidence_text()


def test_row_has_label_does_not_match_b20_as_b2() -> None:
    row = complete_row("ledger-officeext-pkg-b20")
    assert row_has_label(row, "ledger-officeext-pkg-b20")
    assert not row_has_label(row, "ledger-officeext-pkg-b2")


def test_audit_rows_requires_object_level_proof() -> None:
    row = complete_row("ledger-officeext-pkg-b1")
    audit = audit_rows([row], expected_count=1)
    assert audit["audit_pass"] is True
    assert audit["failures"] == {}


def test_audit_rows_rejects_package_level_oracle() -> None:
    row = complete_row("ledger-officeext-pkg-b1")
    row["sibling_unexpected_semantic_mutation_count"] = 1
    audit = audit_rows([row], expected_count=1)
    assert audit["audit_pass"] is False
    assert audit["failures"]["sibling_unchanged"] == ["row-1"]


def test_active_office_runners_ignores_pew_notify(monkeypatch) -> None:
    class Result:
        stdout = "123 pew notify PowerPoint\n456 osascript office_open_gate.applescript\n"

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: Result())
    assert active_office_runners() == ["456 osascript office_open_gate.applescript"]


def test_active_office_runners_ignores_idle_powerpoint_app(monkeypatch) -> None:
    class Result:
        stdout = "456 /Applications/Microsoft PowerPoint.app/Contents/MacOS/Microsoft PowerPoint\n"

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: Result())
    assert active_office_runners() == []


def test_parse_args_supports_boundary_skip_and_checkpoint() -> None:
    args = parse_args(["--checkpoint", "/tmp/checkpoint.json", "--skip-known-boundary"])

    assert args.skip_known_boundary is True
    assert args.checkpoint == "/tmp/checkpoint.json"


def test_checkpoint_records_only_promoted_packages(tmp_path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    record = {"status": "promoted", "candidate": {"package_id": "pkg-1"}}

    update_checkpoint(str(checkpoint), record)

    assert checkpoint_packages(str(checkpoint)) == {"pkg-1"}
    assert read_checkpoint(str(checkpoint))["records"] == [record]


def test_run_candidates_continues_after_failed_candidate(monkeypatch, tmp_path) -> None:
    args = parse_args(["--execute", "--run-office", "--checkpoint", str(tmp_path / "checkpoint.json")])
    candidates = [
        Candidate("pkg-fail", "label-fail", 1, 1, 0, "office_extension"),
        Candidate("pkg-pass", "label-pass", 2, 2, 0, "office_extension"),
    ]
    monkeypatch.setattr("former_preserve_only_promote_loop.active_office_runners", lambda: [])
    monkeypatch.setattr(
        "former_preserve_only_promote_loop.run_candidate",
        lambda candidate, args: 1 if candidate.package_id == "pkg-fail" else 0,
    )
    monkeypatch.setattr(
        "former_preserve_only_promote_loop.audit_labels",
        lambda labels, expected: {"audit_pass": True, "row_count": expected},
    )

    completed = run_candidates(candidates, args)

    assert [row["status"] for row in completed] == ["boundary_or_failed", "promoted"]
    assert checkpoint_packages(args.checkpoint) == {"pkg-pass"}


def test_batch_summary_counts_promotions_boundaries_and_path_metrics(monkeypatch) -> None:
    candidates = [
        Candidate("pkg-fail", "a", 1, 1, 4, "office_extension"),
        Candidate("pkg-pass", "b", 2, 2, 6, "office_extension"),
    ]
    completed = [
        {"status": "boundary_or_failed", "candidate": candidates[0].__dict__},
        {"status": "promoted", "candidate": candidates[1].__dict__, "audit": {"audit_pass": True, "row_count": 2}},
    ]
    args = parse_args([])
    args.skipped_known_boundary_count = 3
    monkeypatch.setattr(
        "former_preserve_only_promote_loop.promotion_metrics",
        lambda rows, out, labels: {
            "repair_dialog_count": 1,
            "unreadable_content_count": 2,
            "close_error_count": 3,
            "security_dialog_count": 4,
            "native_office_pass_count": 5,
            "api_path_pass_count": 6,
            "cli_path_pass_count": 7,
            "mcp_path_pass_count": 8,
        },
    )

    summary = batch_summary(candidates, completed, {}, {}, args, 0)

    assert summary["selected_package_count"] == 2
    assert summary["boundary_package_count"] == 1
    assert summary["promoted_row_count"] == 2
    assert summary["skipped_known_boundary_count"] == 3
    assert summary["skipped_policy_count"] == 10
    assert summary["repair_dialog_count"] == 1
    assert summary["unreadable_content_count"] == 2
    assert summary["close_error_count"] == 3
    assert summary["security_dialog_count"] == 4
    assert summary["native_office_pass_count"] == 5
    assert summary["api_path_pass_count"] == 6
    assert summary["cli_path_pass_count"] == 7
    assert summary["mcp_path_pass_count"] == 8
