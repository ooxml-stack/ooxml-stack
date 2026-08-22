from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_batch_metrics import promotion_metrics


def test_promotion_metrics_counts_public_paths_and_office_dialogs(tmp_path) -> None:
    out = tmp_path / "campaign"
    rows = out / "promotion-rows.jsonl"
    office = out / "office-results"
    office.mkdir(parents=True)
    label = "ledger-officeext-demo-b1"
    rows.write_text(json.dumps(_row(label)) + "\n", encoding="utf-8")
    _write_office(office / f"api-{label}-demo.json")

    metrics = promotion_metrics(rows, out, [label])

    assert metrics["api_path_pass_count"] == 1
    assert metrics["cli_path_pass_count"] == 1
    assert metrics["mcp_path_pass_count"] == 1
    assert metrics["native_office_pass_count"] == 1
    assert metrics["repair_dialog_count"] == 2
    assert metrics["unreadable_content_count"] == 1
    assert metrics["security_dialog_count"] == 1
    assert metrics["close_error_count"] == 1


def _row(label: str) -> dict:
    return {
        "semantic_edit_pass": True,
        "cli_path_checked": True,
        "cli_return_code": 0,
        "mcp_path_checked": True,
        "mcp_return_code": 0,
        "native_office_result": "pass",
        "office_result_id": f"release-evidence/office-results/api-{label}-demo.json",
    }


def _write_office(path: Path) -> None:
    data = {
        "summary": {
            "repair_dialog_count": 2,
            "unreadable_content_count": 1,
            "security_dialog_count": 1,
        },
        "results": [{"status": "pass"}, {"status": "close_error"}],
    }
    path.write_text(json.dumps(data), encoding="utf-8")
