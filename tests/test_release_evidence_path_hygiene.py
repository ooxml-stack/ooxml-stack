from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from redact_release_evidence_paths import redact_user_paths


ROOT = Path(__file__).resolve().parents[1]


def test_redact_user_paths_handles_repo_and_arbitrary_paths() -> None:
    user_prefix = "/" + "Users/"
    repo_file = ROOT / "release-evidence/x.docx"
    outside_file = f"{user_prefix}someone/Library/Mobile Documents/example/Output.pptx"
    text = f"open {repo_file} and {outside_file}"

    redacted = redact_user_paths(text, ROOT)

    assert user_prefix not in redacted
    assert "<repo>/release-evidence/x.docx" in redacted
    assert "<local-path>.pptx" in redacted


def test_tracked_release_evidence_json_has_no_user_paths() -> None:
    result = subprocess.run(
        ["git", "ls-files", "release-evidence/**/*.json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    leaks = [
        path
        for path in result.stdout.splitlines()
        if (ROOT / path).is_file() and "/" + "Users/" in (ROOT / path).read_text(encoding="utf-8")
    ]

    assert leaks == []
