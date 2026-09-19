"""The published plan's basis: each policy node's own default branch.

The plan is a fact about what each repository publishes, and the drift job
defines that as the default branch. A workspace prepared by hand sits on whatever
branch the author was using - `python-docx` and `python-pptx` default to
`master`, not `main` - so the preparation itself has to be the thing under test,
not a convention in a document.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from scripts.ooxml_ci import workspace


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def _remote(tmp_path, name, default_branch, other_branch, content):
    """A bare remote whose default branch and ``main`` hold different content."""
    seed = tmp_path / "seed" / name
    seed.mkdir(parents=True)
    _git(seed, "init", "--quiet", "-b", default_branch)
    for key, value in (("user.email", "ci@example.invalid"), ("user.name", "CI fixture"),
                       ("commit.gpgsign", "false")):
        _git(seed, "config", key, value)
    (seed / "marker.txt").write_text(content[default_branch])
    _git(seed, "add", ".")
    _git(seed, "commit", "--quiet", "-m", default_branch)
    if other_branch:
        _git(seed, "checkout", "--quiet", "-b", other_branch)
        (seed / "marker.txt").write_text(content[other_branch])
        _git(seed, "commit", "--quiet", "-am", other_branch)
        _git(seed, "checkout", "--quiet", default_branch)
    bare = tmp_path / "remotes" / f"{name}.git"
    bare.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--quiet", "--bare", str(seed), str(bare)], check=True,
                   capture_output=True)
    _git(bare, "symbolic-ref", "HEAD", f"refs/heads/{default_branch}")
    return bare


def _policy(tmp_path, keys):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"nodes": [{"key": key} for key in keys]}))
    return path


def test_preparation_uses_each_repositorys_own_default_branch(tmp_path, monkeypatch):
    """`master` stays `master`, and a divergent `main` is not what gets checked out."""
    _remote(tmp_path, "alpha", "master", "main", {"master": "alpha-master\n", "main": "alpha-main\n"})
    _remote(tmp_path, "beta", "main", "master", {"main": "beta-main\n", "master": "beta-master\n"})
    monkeypatch.setattr(workspace, "clone_url",
                        lambda key, owner=workspace.DEFAULT_OWNER: str(tmp_path / "remotes" / f"{key}.git"))

    root = tmp_path / "basis"
    cloned = workspace.prepare(root, _policy(tmp_path, ["alpha", "beta"]))

    assert cloned == ["alpha", "beta"]
    assert (root / "alpha/marker.txt").read_text() == "alpha-master\n"
    assert (root / "beta/marker.txt").read_text() == "beta-main\n"
    assert _git(root / "alpha", "rev-parse", "--abbrev-ref", "HEAD") == "master"
    assert _git(root / "beta", "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_the_node_set_comes_from_the_policy(tmp_path):
    policy = _policy(tmp_path, ["one", "two", "three"])
    assert workspace.node_keys(policy) == ["one", "two", "three"]


def test_preparation_refuses_to_reuse_an_existing_workspace(tmp_path):
    """A half-populated directory must not be read as a prepared basis."""
    root = tmp_path / "basis"
    (root / "alpha").mkdir(parents=True)
    with pytest.raises(workspace.WorkspaceError, match="already exists"):
        workspace.prepare(root, _policy(tmp_path, ["alpha"]))