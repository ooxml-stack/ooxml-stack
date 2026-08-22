from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_evidence_retention import forbidden_evidence_paths, read_allowlist, status_path


def test_blocks_new_office_packages_under_release_evidence() -> None:
    paths = [
        "release-evidence/p99/output.pptx",
        "release-evidence/p99/output.docx",
        "release-evidence/p99/run.jsonl",
    ]

    assert forbidden_evidence_paths(paths, []) == [
        "release-evidence/p99/output.docx",
        "release-evidence/p99/output.pptx",
    ]


def test_allows_non_office_and_non_evidence_paths() -> None:
    paths = [
        "release-evidence/p99/run.json",
        "release-evidence/p99/run.jsonl",
        "tests/fixtures/sample.pptx",
    ]

    assert forbidden_evidence_paths(paths, []) == []


def test_allows_explicit_retained_artifacts() -> None:
    paths = [
        "release-evidence/failures/repair-dialog-001.pptx",
        "release-evidence/p99/ordinary-success.pptx",
    ]
    allowlist = ["release-evidence/failures/*.pptx"]

    assert forbidden_evidence_paths(paths, allowlist) == ["release-evidence/p99/ordinary-success.pptx"]


def test_read_allowlist_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "allowlist.txt"
    path.write_text("\n# keep failures\nrelease-evidence/failures/*.docx\n", encoding="utf-8")

    assert read_allowlist(path) == ["release-evidence/failures/*.docx"]


def test_status_path_handles_diff_and_porcelain_renames() -> None:
    assert status_path("A\trelease-evidence/p99/output.pptx") == "release-evidence/p99/output.pptx"
    assert status_path("R100\told.pptx\trelease-evidence/p99/output.pptx") == "release-evidence/p99/output.pptx"
    assert status_path("old.pptx -> release-evidence/p99/output.pptx") == "release-evidence/p99/output.pptx"
