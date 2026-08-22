from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_evidence_artifacts import collect_artifacts, summarize


def test_audit_evidence_artifacts_reports_hardlink_savings(tmp_path: Path) -> None:
    root = tmp_path
    evidence = root / "release-evidence" / "run"
    evidence.mkdir(parents=True)
    left = evidence / "left.pptx"
    right = evidence / "right.pptx"
    left.write_bytes(b"same")
    right.hardlink_to(left)

    summary = summarize(collect_artifacts(root / "release-evidence", root))

    assert summary["file_count"] == 2
    assert summary["logical_bytes"] == 8
    assert summary["hardlink_physical_bytes"] == 4
    assert summary["hardlink_saved_bytes"] == 4


def test_audit_evidence_artifacts_hashes_duplicate_content(tmp_path: Path) -> None:
    root = tmp_path
    evidence = root / "release-evidence" / "run"
    evidence.mkdir(parents=True)
    (evidence / "left.docx").write_bytes(b"same")
    (evidence / "right.docx").write_bytes(b"same")

    summary = summarize(collect_artifacts(root / "release-evidence", root, hash_content=True))

    assert summary["content_hashes_computed"] is True
    assert summary["content_unique_count"] == 1
    assert summary["content_duplicate_bytes"] == 4
