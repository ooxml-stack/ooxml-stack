"""Adapter provenance: the adapter and its imports come from the snapshot.

The runner is normally started from a repository's own CI entry point, so the
calling process has already imported *its* ``scripts.ci`` package. Importing the
adapter out of a snapshot in that process would hand the adapter the caller's
modules, because ``from scripts.ci import helper`` resolves through the loaded
parent package rather than through the snapshot that was just put on
``sys.path``.

Every case here asserts observable behaviour (the stage list and the name the
helper reports), not ``__file__``, so a loader that merely relabels the module
still fails.
"""

from __future__ import annotations

import contextlib
import importlib
import subprocess
import sys

import pytest
from runner_fixtures import (
    REPO,
    RUNNER_COMMIT,
    commit_all,
    make_helper_repo,
    make_plan,
    rewrite_helper,
)

from ooxml_runner import adapter as adapters
from ooxml_runner import cli, snapshot

BROKEN_ADAPTER = '''
"""Fixture adapter that cannot be imported."""

import not_a_real_module_anywhere


def describe(root):
    return {"stages": ["broken"]}
'''


def _describe(root, repo, plan, commit="HEAD"):
    return cli.describe_repository(
        root=root, repo=repo, commit=commit, runner_commit=RUNNER_COMMIT, plan=plan
    )


def _behaviour(described):
    return described["stages"], described["implementation"]


@contextlib.contextmanager
def _caller_package_loaded(caller, expected_name="caller"):
    """Leave the caller's own ``scripts.ci.helper`` imported for the duration.

    This reproduces the state ``python -m scripts.ci.run`` is in before it ever
    looks at a snapshot: the parent package is already resolved and cached.
    """
    saved = dict(sys.modules)
    sys.path.insert(0, str(caller))
    try:
        module = importlib.import_module("scripts.ci.helper")
        assert module.NAME == expected_name
        yield module
    finally:
        sys.path.remove(str(caller))
        for name in [name for name in sys.modules if name not in saved]:
            del sys.modules[name]
        sys.modules.update(saved)


def test_a_clean_checkout_reports_the_committed_adapter(tmp_path):
    repo = make_helper_repo(tmp_path, REPO, ("alpha", "beta"), helper_name="committed")
    plan = make_plan(tmp_path, repo)
    assert _behaviour(_describe(tmp_path, REPO, plan)) == (["alpha", "beta"], "committed")


def test_an_uncommitted_caller_edit_does_not_change_the_verified_commit(tmp_path):
    """The control the review used: dirty the caller, verify the same commit.

    The caller here is the repository under test, exactly as it is when the
    engine's own ``python -m scripts.ci.run`` verifies the engine.
    """
    repo = make_helper_repo(tmp_path, REPO, ("alpha", "beta"), helper_name="committed")
    plan = make_plan(tmp_path, repo)

    rewrite_helper(repo, "dirty", ("wrong-environment",))
    with _caller_package_loaded(repo, expected_name="dirty"):
        assert _behaviour(_describe(tmp_path, REPO, plan)) == (["alpha", "beta"], "committed")


def test_a_preloaded_caller_package_does_not_win_over_the_snapshot(tmp_path):
    """The caller's already-imported ``scripts.ci`` must not serve the adapter."""
    caller = make_helper_repo(tmp_path, "caller", ("wrong",), helper_name="caller")
    repo = make_helper_repo(tmp_path, REPO, ("alpha",), helper_name="committed")
    plan = make_plan(tmp_path, repo)

    with _caller_package_loaded(caller):
        assert _behaviour(_describe(tmp_path, REPO, plan)) == (["alpha"], "committed")


def test_two_repositories_with_the_same_module_name_keep_their_own_adapter(tmp_path):
    first = make_helper_repo(tmp_path, "repo-a", ("alpha",), helper_name="a")
    second = make_helper_repo(tmp_path, "repo-b", ("beta",), helper_name="b")
    plan_a = make_plan(tmp_path, first, key="repo-a")
    plan_b = make_plan(tmp_path, second, key="repo-b", name="plan-b.json")

    assert _behaviour(_describe(tmp_path, "repo-a", plan_a)) == (["alpha"], "a")
    assert _behaviour(_describe(tmp_path, "repo-b", plan_b)) == (["beta"], "b")


def test_two_commits_of_one_repository_keep_their_own_helper(tmp_path):
    repo = make_helper_repo(tmp_path, REPO, ("alpha",), helper_name="first")
    plan = make_plan(tmp_path, repo)
    first = snapshot.resolve_commit(repo, "HEAD")
    rewrite_helper(repo, "second", ("beta",))
    second = commit_all(repo, "second helper")

    assert _behaviour(_describe(tmp_path, REPO, plan, commit=first)) == (["alpha"], "first")
    assert _behaviour(_describe(tmp_path, REPO, plan, commit=second)) == (["beta"], "second")


def test_a_missing_adapter_fails_closed_instead_of_using_the_caller(tmp_path):
    """The caller has ``scripts.ci.missing``; the verified commit does not."""
    caller = make_helper_repo(tmp_path, "caller", ("wrong",), helper_name="caller")
    (caller / "scripts/ci/missing.py").write_text("def describe(root): return {'stages': ['wrong']}\n")
    repo = make_helper_repo(tmp_path, REPO, ("alpha",), helper_name="committed")
    plan = make_plan(tmp_path, repo, adapter="scripts.ci.missing")

    with _caller_package_loaded(caller), pytest.raises(adapters.AdapterError, match="missing"):
        _describe(tmp_path, REPO, plan)


def test_an_adapter_that_cannot_import_fails_closed(tmp_path):
    repo = make_helper_repo(tmp_path, REPO, ("alpha",), adapter=BROKEN_ADAPTER)
    plan = make_plan(tmp_path, repo)
    with pytest.raises(adapters.AdapterError, match="failed to import"):
        _describe(tmp_path, REPO, plan)


def test_the_adapter_worker_is_importable_and_declares_its_operations():
    """The worker is a real module with a clear protocol, not a shell string."""
    probe = "import ooxml_runner.adapter_worker as w; print(sorted(w.OPERATIONS))"
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    assert "'describe'" in result.stdout and "'verify_report'" in result.stdout