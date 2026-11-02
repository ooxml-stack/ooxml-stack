from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from artifact_paths import artifact_dir, artifact_file


def test_artifact_file_resolves_single_output_under_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OOXML_ARTIFACT_ROOT", str(tmp_path))
    path = artifact_file("release-evidence", "reports/run.json")
    assert path == (tmp_path / "ooxml-stack" / "release-evidence" / "reports" / "run.json").resolve()
    assert path.parent.is_dir()


def test_artifact_file_rejects_escape_and_git_targets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OOXML_ARTIFACT_ROOT", str(tmp_path))
    for bad in ("/etc/passwd", "../escape.json", ".git/config", "sub/../../out.json"):
        with pytest.raises(ValueError):
            artifact_file("release-evidence", bad)


def test_artifact_file_without_ensure_creates_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OOXML_ARTIFACT_ROOT", str(tmp_path))
    path = artifact_file("release-evidence", "x/y.json", ensure=False)
    assert not path.exists()


def test_artifact_dir_refuses_git_checkout(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OOXML_ARTIFACT_ROOT", str(tmp_path / "repo"))
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    with pytest.raises(ValueError):
        artifact_dir()
