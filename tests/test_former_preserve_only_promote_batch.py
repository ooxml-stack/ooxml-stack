import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import former_preserve_only_promote_batch as runner


def test_required_before_value_filters_default_attribute(monkeypatch, tmp_path):
    row = {
        "family": "office_extension",
        "source_row_id": "source-1",
        "blocker_type": "semantic_value_available_pending_proof",
        "qname": "{wps}cNvSpPr",
        "package_id": "pkg",
        "input_file": "pkg.docx",
        "part_name": "word/document.xml",
        "selector": "/wps:cNvSpPr",
    }
    args = argparse.Namespace(
        family="office_extension",
        qname_contains=["cNvSpPr"],
        package_id="pkg",
        max_package_mb=0,
        attribute_name="txBox",
        required_before_value="1",
    )
    (tmp_path / "pkg.docx").touch()
    monkeypatch.setattr(runner, "CORPUS", tmp_path)
    monkeypatch.setattr(runner, "_read_value", lambda *unused: "")
    assert runner._eligible(row, args, set()) is False
    monkeypatch.setattr(runner, "_read_value", lambda *unused: "1")
    assert runner._eligible(row, args, set()) is True
