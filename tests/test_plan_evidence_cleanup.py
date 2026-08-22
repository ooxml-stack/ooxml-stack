from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from plan_evidence_cleanup import cleanup_candidate, main, normalize_path, output_paths, plan_cleanup, row_disposition


def test_output_paths_finds_nested_office_outputs() -> None:
    row = {
        "output_file": "ooxml-stack/release-evidence/p90/p80-promotion-outputs/a.docx",
        "cli": {"output_file": "release-evidence/p90/p80-promotion-public-paths/a.pptx"},
        "summary": "not a file",
    }

    assert output_paths(row) == [
        "ooxml-stack/release-evidence/p90/p80-promotion-outputs/a.docx",
        "release-evidence/p90/p80-promotion-public-paths/a.pptx",
    ]


def test_row_disposition_classifies_pass_and_fail() -> None:
    assert row_disposition({"pass": True, "native_office_result": "pass"}) == "pass"
    assert row_disposition({"pass": True, "native_office_result": "repair_dialog"}) == "fail"
    assert row_disposition({"note": "no status"}) == "unknown"


def test_cleanup_candidate_requires_generated_dir_and_all_pass() -> None:
    path = "release-evidence/p90/p80-promotion-outputs/a.docx"

    assert cleanup_candidate(path, ["pass", "pass"])
    assert not cleanup_candidate(path, ["pass", "fail"])
    assert not cleanup_candidate("release-evidence/p83/outputs/a.docx", ["pass"])


def test_normalize_path_strips_repo_prefix(tmp_path: Path) -> None:
    path = "ooxml-stack/release-evidence/p90/out.docx"

    assert normalize_path(path, tmp_path) == "release-evidence/p90/out.docx"


def test_summarize_estimates_releasable_hardlinked_bytes() -> None:
    artifacts = [
        {"path": "release-evidence/p90/p80-promotion-outputs/a.docx", "size": 10, "dev": 1, "ino": 1, "nlink": 2},
        {"path": "release-evidence/p90/p80-promotion-outputs/b.docx", "size": 10, "dev": 1, "ino": 1, "nlink": 2},
        {"path": "release-evidence/p83/outputs/c.docx", "size": 5, "dev": 1, "ino": 2, "nlink": 1},
    ]
    refs = {
        "release-evidence/p90/p80-promotion-outputs/a.docx": ["pass"],
        "release-evidence/p90/p80-promotion-outputs/b.docx": ["pass"],
        "release-evidence/p83/outputs/c.docx": ["pass"],
    }

    summary, candidates = plan_cleanup(artifacts, refs)

    assert summary["cleanup_candidates"]["file_count"] == 2
    assert summary["cleanup_candidates"]["estimated_releasable_bytes"] == 10
    assert summary["kept_or_unknown"]["file_count"] == 1
    assert [item["path"] for item in candidates] == [
        "release-evidence/p90/p80-promotion-outputs/a.docx",
        "release-evidence/p90/p80-promotion-outputs/b.docx",
    ]


def test_empty_candidate_list_has_zero_lines(tmp_path: Path) -> None:
    out = tmp_path / "plan.json"
    candidates = tmp_path / "candidates.txt"

    assert main(["--root", str(tmp_path), "-o", str(out), "--candidate-list", str(candidates)]) == 0
    assert candidates.read_text(encoding="utf-8") == ""
