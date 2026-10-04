"""Workspace instructions remain portable without replacing local instructions."""

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.workspace_agents import install

ROOT = Path(__file__).resolve().parents[1]
RELATIVE_SOURCE = Path("ooxml-stack/docs/WORKSPACE-AGENTS.md")


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "work space"
    source = root / RELATIVE_SOURCE
    source.parent.mkdir(parents=True)
    source.write_text("# Shared workspace rules\n")
    return root


def _cli(workspace):
    return subprocess.run(
        [sys.executable, "-m", "scripts.workspace_agents", "--workspace", str(workspace)],
        cwd=ROOT, capture_output=True, text=True, check=False)


def test_cli_install_is_relative_idempotent_and_follows_canonical_edits(workspace):
    for _ in range(2):
        result = _cli(workspace)
        assert result.returncode == 0, result.stderr
        assert Path(result.stdout.strip()) == workspace / "AGENTS.md"
    target = workspace / "AGENTS.md"
    assert target.is_symlink()
    assert target.readlink() == RELATIVE_SOURCE
    assert target.read_text() == "# Shared workspace rules\n"
    (workspace / RELATIVE_SOURCE).write_text("# Updated rules\n")
    assert target.read_text() == "# Updated rules\n"
    moved = workspace.rename(workspace.with_name("moved workspace"))
    assert (moved / "AGENTS.md").read_text() == "# Updated rules\n"
    assert install(moved) == moved / "AGENTS.md"


@pytest.mark.parametrize("kind", ["file", "identical-file", "directory", "symlink", "dangling", "absolute"])
def test_existing_instructions_are_preserved_on_refusal(workspace, kind):
    target = workspace / "AGENTS.md"
    other = workspace / "local.md"
    other.write_text("# Local rules\n")
    if kind in {"file", "identical-file"}:
        target.write_text(other.read_text() if kind == "file" else
                          (workspace / RELATIVE_SOURCE).read_text())
    elif kind == "directory":
        target.mkdir()
        (target / "keep.md").write_text("keep\n")
    else:
        dest = {"symlink": Path("local.md"), "dangling": Path("absent.md"),
                "absolute": workspace / RELATIVE_SOURCE}[kind]
        target.symlink_to(dest)
    before = target.lstat()
    content = target.read_bytes() if target.is_file() else None
    link = target.readlink() if target.is_symlink() else None
    result = _cli(workspace)
    assert result.returncode == 1
    assert "already exists" in result.stderr
    after = target.lstat()
    for field in ("st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns"):
        assert getattr(after, field) == getattr(before, field)
    if content is not None:
        assert target.read_bytes() == content
    if link is not None:
        assert target.readlink() == link
    if kind == "directory":
        assert (target / "keep.md").read_text() == "keep\n"
    assert other.read_text() == "# Local rules\n"


@pytest.mark.parametrize("kind", ["missing", "directory", "source-symlink", "docs-symlink", "repo-symlink"])
def test_missing_or_redirected_canonical_source_is_refused(workspace, kind):
    source = workspace / RELATIVE_SOURCE
    if kind in {"missing", "directory"}:
        source.unlink()
        if kind == "directory":
            source.mkdir()
    else:
        original = {"source-symlink": source, "docs-symlink": source.parent,
                    "repo-symlink": source.parent.parent}[kind]
        moved = original.rename(workspace / "redirected")
        original.symlink_to(moved, target_is_directory=moved.is_dir())
    result = _cli(workspace)
    assert result.returncode == 1
    assert "canonical" in result.stderr
    assert not (workspace / "AGENTS.md").exists()
    assert not (workspace / "AGENTS.md").is_symlink()


def test_make_entry_installs_and_propagates_refusal(workspace):
    command = ["make", "workspace-init", f"WORKSPACE={workspace}"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (workspace / "AGENTS.md").readlink() == RELATIVE_SOURCE
    (workspace / "AGENTS.md").unlink()
    (workspace / "AGENTS.md").write_text("keep\n")
    refused = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert refused.returncode != 0
    assert (workspace / "AGENTS.md").read_text() == "keep\n"


def test_workspace_must_be_explicit_and_exist(tmp_path):
    with pytest.raises(ValueError, match="nonempty"):
        install("")
    result = _cli(tmp_path / "absent")
    assert result.returncode == 1
    assert not (tmp_path / "absent").exists()
