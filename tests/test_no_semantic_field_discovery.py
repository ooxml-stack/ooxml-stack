from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_no_semantic_field_discovery import build_discovery


def test_no_semantic_discovery_classifies_empty_context_and_scalar(tmp_path: Path) -> None:
    _write_docx(tmp_path / "corpus/docx/sample.docx")
    rows = [
        _row("empty", "/w:document/w:body/w:p[1]/w:r/w:pict/v:shape/v:formulas"),
        _row("context", "/w:document/w:body/w:p[2]/w:r/w:pict/v:shape/v:formulas"),
        _row("scalar", "/w:document/w:body/w:p[3]/w:r/w:pict/v:shape/v:textbox"),
        _row("identity", "/w:document/w:body/w:p[1]/w:r/w:pict/v:shape/v:formulas", "relationship_identity_like"),
    ]

    summary = build_discovery(rows, tmp_path)

    assert summary["input_row_count"] == 3
    assert summary["classification_counts"] == {
        "empty_structural_container": 1,
        "context_only_structural_container": 1,
        "unexpected_target_scalar": 1,
    }
    assert summary["recommended_action_counts"] == {
        "keep_unsupported": 1,
        "investigate_context_model": 1,
        "rebuild_gap_or_add_policy": 1,
    }


def _row(row_id: str, selector: str, blocker: str = "needs_family_model") -> dict:
    return {
        "row_id": row_id,
        "package_id": "sample",
        "input_file": "corpus/docx/sample.docx",
        "part_name": "word/document.xml",
        "selector": selector,
        "family": "vml_drawing",
        "qname": "{urn:schemas-microsoft-com:vml}formulas",
        "blocker_type": blocker,
        "semantic_value_kind": "no_descendant_value",
    }


def _write_docx(path: Path) -> None:
    path.parent.mkdir(parents=True)
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xmlns:v="urn:schemas-microsoft-com:vml">
  <w:body>
    <w:p><w:r><w:pict><v:shape><v:formulas/></v:shape></w:pict></w:r></w:p>
    <w:p><w:r><w:pict><v:shape><v:formulas/><v:path textboxrect="0,0,1,1"/></v:shape></w:pict></w:r></w:p>
    <w:p><w:r><w:pict><v:shape><v:textbox inset="0,0,0,0"/></v:shape></w:pict></w:r></w:p>
  </w:body>
</w:document>
"""
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("word/document.xml", xml)
