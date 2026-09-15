"""Runner identity: the pinned commit constrains the source that actually runs.

The runner proves which version of itself executed. Comparing the checkout's
``HEAD`` is not enough: the working tree can be edited without moving ``HEAD``,
and a read-only mount says nothing about what the mount contains. The trusted
hash is therefore derived from the pinned commit's own tree, and the running
package has to match it.

These tests use a disposable runner checkout so they never touch the package
that is executing them.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import ooxml_runner
from ooxml_runner import identity, snapshot

PACKAGE = Path(ooxml_runner.__file__).resolve().parent


def make_runner_checkout(tmp_path, name="runner"):
    """A clean Git checkout holding a copy of the runner package."""
    root = tmp_path / name
    (root / "ooxml_runner").mkdir(parents=True)
    for source in sorted(PACKAGE.glob("*.py")):
        shutil.copy2(source, root / "ooxml_runner" / source.name)
    (root / "docs").mkdir()
    (root / "docs/notes.md").write_text("unrelated documentation\n")
    snapshot.git(root, "init", "--quiet")
    for key, value in (("user.email", "ci@example.invalid"), ("user.name", "CI fixture"),
                       ("commit.gpgsign", "false"), ("core.hooksPath", "/dev/null")):
        snapshot.git(root, "config", key, value)
    snapshot.git(root, "add", ".")
    snapshot.git(root, "commit", "--quiet", "-m", "runner fixture")
    return root


def _identity(root):
    return identity.identity(package_dir=root / "ooxml_runner", runner_root=root)


def test_a_clean_checkout_matches_the_commit_it_is_pinned_to(tmp_path):
    root = make_runner_checkout(tmp_path)
    observed = _identity(root)
    trusted = identity.require_expected(observed, observed["commit"])
    assert trusted["commit"] == observed["commit"]
    assert trusted["source_sha256"] == observed["source_sha256"]
    assert trusted["source_sha256"] == identity.source_sha256_at(root, observed["commit"])


def test_editing_the_running_source_is_refused_even_though_head_is_unchanged(tmp_path):
    root = make_runner_checkout(tmp_path)
    observed = _identity(root)
    target = root / "ooxml_runner/docker.py"
    target.write_text(target.read_text().replace("MAX_CPUS = 4", "MAX_CPUS = 3"))

    assert snapshot.git(root, "rev-parse", "HEAD") == observed["commit"]
    with pytest.raises(identity.IdentityError, match="source"):
        identity.require_expected(_identity(root), observed["commit"])


def test_adding_a_runner_source_file_is_refused(tmp_path):
    root = make_runner_checkout(tmp_path)
    observed = _identity(root)
    (root / "ooxml_runner/extra.py").write_text("EXTRA = 1\n")

    with pytest.raises(identity.IdentityError, match="source"):
        identity.require_expected(_identity(root), observed["commit"])


def test_deleting_a_runner_source_file_is_refused(tmp_path):
    root = make_runner_checkout(tmp_path)
    observed = _identity(root)
    (root / "ooxml_runner/plan.py").unlink()

    with pytest.raises(identity.IdentityError, match="source"):
        identity.require_expected(_identity(root), observed["commit"])


def test_an_unrelated_change_in_the_runner_checkout_is_allowed(tmp_path):
    """Only the executed package is in scope, not other authors' files."""
    root = make_runner_checkout(tmp_path)
    observed = _identity(root)
    (root / "docs/notes.md").write_text("someone else's documentation\n")
    (root / "docs/extra.md").write_text("new documentation\n")

    trusted = identity.require_expected(_identity(root), observed["commit"])
    assert trusted["source_sha256"] == observed["source_sha256"]


def test_a_checkout_that_is_not_the_pinned_commit_is_refused(tmp_path):
    root = make_runner_checkout(tmp_path)
    observed = _identity(root)
    with pytest.raises(identity.IdentityError, match="commit mismatch"):
        identity.require_expected(observed, "0" * 40)


def test_the_trusted_hash_comes_from_the_commit_not_the_worktree(tmp_path):
    """A dirty worktree must not be able to define its own expectation."""
    root = make_runner_checkout(tmp_path)
    observed = _identity(root)
    trusted = identity.source_sha256_at(root, observed["commit"])
    target = root / "ooxml_runner/docker.py"
    target.write_text(target.read_text().replace("MAX_CPUS = 4", "MAX_CPUS = 3"))

    assert identity.source_sha256(root / "ooxml_runner") != trusted
    assert identity.source_sha256_at(root, observed["commit"]) == trusted