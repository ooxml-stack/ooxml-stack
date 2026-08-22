from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from former_preserve_only_office_boundaries import failed_office_packages


def test_gate_pass_with_dialog_remains_boundary(tmp_path: Path):
    data = {
        "summary": {"gate_pass": True},
        "results": [{"file": "api-x-docx_dialog.docx", "status": "pass_with_dialog"}],
    }
    (tmp_path / "api-dialog.json").write_text(json.dumps(data))
    assert failed_office_packages(tmp_path) == {"docx_dialog"}


def test_plain_pass_is_not_boundary(tmp_path: Path):
    data = {
        "summary": {"gate_pass": True},
        "results": [{"file": "api-x-pptx_plain.pptx", "status": "pass"}],
    }
    (tmp_path / "api-pass.json").write_text(json.dumps(data))
    assert failed_office_packages(tmp_path) == set()
