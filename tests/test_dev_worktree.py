"""Developer worktrees preserve existing work and stay within the task container."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import dev_worktree

ROOT = Path(__file__).resolve().parents[1]


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def workspace(tmp_path):
    repo = tmp_path / "alpha"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    for key, value in (("user.name", "Fixture"), ("user.email", "test@example.invalid"),
                       ("commit.gpgsign", "false"), ("core.hooksPath", "/dev/null")):
        _git(repo, "config", key, value)
    (repo / "source.txt").write_text("committed\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "--quiet", "-m", "fixture")
    return tmp_path


def _create(root, **overrides):
    args = {"workspace": root, "task": "review", "repository": "alpha",
            "owner": "developer", "retire_when": "merged and evidence retained"}
    return dev_worktree.create(**{**args, **overrides})


def _record(root):
    return json.loads((root / ".worktrees/review/alpha.worktree.json").read_text())


def test_cli_creates_a_recorded_checkout_without_changing_source(workspace):
    source = workspace / "alpha"
    (source / "source.txt").write_text("another developer's edits\n")
    (source / "untracked.txt").write_text("keep\n")
    before = _git(source, "status", "--porcelain")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.dev_worktree", "--workspace", str(workspace),
         "--task", "review", "--repository", "alpha", "--owner", "developer",
         "--retire-when", "merged and evidence retained", "--branch", "review-fix"],
        cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    target = workspace / ".worktrees/review/alpha"
    assert Path(result.stdout.strip()) == target
    assert (target / "source.txt").read_text() == "committed\n"
    assert _git(target, "branch", "--show-current") == "review-fix"
    record = _record(workspace)
    assert record["status"] == "ready"
    assert record["owner"] == "developer"
    assert record["retire_when"] == "merged and evidence retained"
    assert record["evidence"] == ".delivery-evidence/review"
    assert record["checkout"] == ".worktrees/review/alpha"
    assert record["commit"] == _git(target, "rev-parse", "HEAD")
    assert _git(source, "status", "--porcelain") == before
    assert (source / "source.txt").read_text() == "another developer's edits\n"
    assert (source / "untracked.txt").read_text() == "keep\n"


@pytest.mark.parametrize("field", ["task", "repository"])
@pytest.mark.parametrize("value", ["../escape", "/outside", "nested/name", ".", ""])
def test_path_components_cannot_escape_the_container(workspace, field, value):
    with pytest.raises(ValueError, match="single name"):
        _create(workspace, **{field: value})
    assert not (workspace / ".worktrees").exists()


@pytest.mark.parametrize("relative", [
    ".worktrees", ".worktrees/review", ".worktrees/review/alpha",
    ".worktrees/review/alpha.worktree.json",
])
def test_symlinks_cannot_redirect_creation(workspace, relative):
    outside = workspace / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep\n")
    link = workspace / relative
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)
    before = _git(workspace / "alpha", "worktree", "list", "--porcelain")
    with pytest.raises(ValueError, match="symlinked"):
        _create(workspace)
    assert list(outside.iterdir()) == [outside / "keep.txt"]
    assert (outside / "keep.txt").read_text() == "keep\n"
    assert _git(workspace / "alpha", "worktree", "list", "--porcelain") == before


@pytest.mark.parametrize("populated", [False, True])
def test_existing_destination_is_never_reused(workspace, populated):
    target = workspace / ".worktrees/review/alpha"
    target.mkdir(parents=True)
    if populated:
        (target / "keep.txt").write_text("keep\n")
    with pytest.raises(ValueError, match="already exists"):
        _create(workspace)
    assert sorted(path.name for path in target.iterdir()) == (["keep.txt"] if populated else [])
    assert not (target.parent / "alpha.worktree.json").exists()


def test_existing_record_is_preserved(workspace):
    parent = workspace / ".worktrees/review"
    parent.mkdir(parents=True)
    record = parent / "alpha.worktree.json"
    record.write_text("original record\n")
    with pytest.raises(ValueError, match="already exists"):
        _create(workspace)
    assert record.read_text() == "original record\n"
    assert not (parent / "alpha").exists()


@pytest.mark.parametrize("field", ["owner", "retire_when"])
def test_unowned_or_unbounded_work_is_refused(workspace, field):
    with pytest.raises(ValueError, match="nonempty"):
        _create(workspace, **{field: " "})
    assert not (workspace / ".worktrees").exists()


def test_invalid_revision_creates_no_task_directory(workspace):
    with pytest.raises(RuntimeError, match="cannot resolve"):
        _create(workspace, revision="missing-revision")
    assert not (workspace / ".worktrees").exists()


def test_make_entry_creates_a_detached_task_checkout(workspace):
    result = subprocess.run(
        ["make", "worktree", f"WORKSPACE={workspace}", "TASK=review",
         "REPOSITORY=alpha", "OWNER=developer", "RETIRE_WHEN=merged"],
        cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    target = workspace / ".worktrees/review/alpha"
    assert _git(target, "branch", "--show-current") == ""
    assert _record(workspace)["status"] == "ready"


def test_git_failure_is_recorded_without_removing_existing_work(workspace):
    source = workspace / "alpha"
    _git(source, "branch", "already-exists")
    before = _git(source, "worktree", "list", "--porcelain")
    with pytest.raises(subprocess.CalledProcessError):
        _create(workspace, branch="already-exists")
    assert _record(workspace)["status"] == "failed"
    assert _git(source, "worktree", "list", "--porcelain") == before
    assert not (workspace / ".worktrees/review/alpha").exists()


def test_interrupted_creation_keeps_a_recoverable_record(workspace, monkeypatch):
    real_git = dev_worktree.git

    def interrupted(source, *args):
        result = real_git(source, *args)
        if args[:2] == ("worktree", "add"):
            raise KeyboardInterrupt()
        return result

    monkeypatch.setattr(dev_worktree, "git", interrupted)
    with pytest.raises(KeyboardInterrupt):
        _create(workspace)
    record = _record(workspace)
    assert record["status"] == "interrupted"
    target = workspace / record["checkout"]
    assert _git(target, "rev-parse", "HEAD") == record["commit"]
    assert (target / "source.txt").read_text() == "committed\n"
