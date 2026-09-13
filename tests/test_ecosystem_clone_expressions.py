"""Actions expressions and shell escapes in ``git clone`` targets.

Each case drives the real CLI over a sealed, no-drift workspace whose only clone
comes from the step under test, so the assertions cover the edge, the impact set
and the exit code together rather than an internal token array.
"""

from __future__ import annotations

import json

import pytest

from ecosystem_fixtures import align_pptx, build_workspace, resolvable_for, seal, write
from ecosystem_workflows_expressions import (
    CORPUS,
    CORE,
    WORKFLOW_EXPR_ACTIONS_REPO,
    WORKFLOW_EXPR_DYNAMIC_BRANCH,
    WORKFLOW_EXPR_EQUALS_BRANCH,
    WORKFLOW_EXPR_EQUALS_DEPTH,
    WORKFLOW_EXPR_ESCAPED,
    WORKFLOW_EXPR_FORMAT_KEEP,
    WORKFLOW_EXPR_FORMAT_STRIP,
    WORKFLOW_EXPR_LITERAL_MARKER,
    WORKFLOW_EXPR_MARKER_COLLISION,
    WORKFLOW_EXPR_MULTILINE_THEN_CLONE,
    WORKFLOW_EXPR_QUOTED_ACTIONS_REPO,
    WORKFLOW_EXPR_QUOTED_DYNAMIC_THEN_STATIC,
    WORKFLOW_EXPR_QUOTED_STATIC,
    WORKFLOW_EXPR_QUOTED_THEN_CLONE,
    WORKFLOW_EXPR_QUOTED_VAR_REPO,
    WORKFLOW_EXPR_STATIC,
    WORKFLOW_EXPR_UNREADABLE,
    WORKFLOW_EXPR_VAR_REPO,
    WORKFLOW_EXPR_VAR_REPO_THEN_STATIC,
)
from scripts.ooxml_ci import cli

PLAN_RELPATH = "ooxml-stack/ci/ecosystem-plan.json"
WORKFLOW_RELPATH = "python-docx/.github/workflows/ci.yml"


def _prepare(tmp_path, monkeypatch, workflow):
    """A sealed, no-drift workspace whose only clone is the step under test."""
    root = build_workspace(tmp_path)
    heads = seal(root)
    align_pptx(root, heads)
    resolvable_for(monkeypatch, heads)
    write(root / WORKFLOW_RELPATH, workflow)
    return root


def _written(root, capsys):
    assert cli.main(["--write", "--root", str(root)]) == 0
    capsys.readouterr()
    return json.loads((root / PLAN_RELPATH).read_text(encoding="utf-8"))


def _clones(plan):
    return [edge for edge in plan["edges"] if edge.get("purpose") == "workflow_clone"]


def _unsupported(plan):
    return [item for item in plan["diagnostics"] if item["code"] == "unsupported_workflow"]


def _assert_one_corpus_edge(plan):
    assert [
        (e["from"], e["to"], e["kind"], e["role"], e["purpose"], e["declared"]["url"])
        for e in _clones(plan)
    ] == [("python-docx", "ooxml-native-corpus", "ci", "ci", "workflow_clone", CORPUS)]
    assert "python-docx" in plan["graphs"]["impact"]["ooxml-native-corpus"]["reaches"]
    assert not [d for d in plan["diagnostics"] if d["code"] == "policy_node_mismatch"]
    assert _unsupported(plan) == []


def _assert_clean_strict(root, capsys):
    assert cli.main(["--check", "--strict", "--root", str(root)]) == 0
    assert "result        : ok" in capsys.readouterr().out


def test_a_static_clone_is_the_control(tmp_path, capsys, monkeypatch):
    root = _prepare(tmp_path, monkeypatch, WORKFLOW_EXPR_STATIC)
    _assert_one_corpus_edge(_written(root, capsys))
    _assert_clean_strict(root, capsys)


def test_a_dynamic_branch_keeps_the_static_repository(tmp_path, capsys, monkeypatch):
    """``--branch ${{ ... }}`` must not consume the URL that follows it."""
    root = _prepare(tmp_path, monkeypatch, WORKFLOW_EXPR_DYNAMIC_BRANCH)
    _assert_one_corpus_edge(_written(root, capsys))
    _assert_clean_strict(root, capsys)


@pytest.mark.parametrize(
    "workflow",
    [WORKFLOW_EXPR_EQUALS_BRANCH, WORKFLOW_EXPR_EQUALS_DEPTH],
    ids=["branch", "depth"],
)
def test_an_equals_form_option_keeps_the_static_repository(tmp_path, capsys, monkeypatch, workflow):
    """``--branch=${{ ... }}`` is a self-contained option, not the repository."""
    root = _prepare(tmp_path, monkeypatch, workflow)
    _assert_one_corpus_edge(_written(root, capsys))
    _assert_clean_strict(root, capsys)


def test_a_double_quoted_static_url_is_still_static(tmp_path, capsys, monkeypatch):
    root = _prepare(tmp_path, monkeypatch, WORKFLOW_EXPR_QUOTED_STATIC)
    _assert_one_corpus_edge(_written(root, capsys))
    _assert_clean_strict(root, capsys)


@pytest.mark.parametrize(
    "workflow",
    [WORKFLOW_EXPR_QUOTED_VAR_REPO, WORKFLOW_EXPR_QUOTED_ACTIONS_REPO],
    ids=["shell-variable", "actions-expression"],
)
def test_a_double_quoted_dynamic_target_is_reported_not_guessed(
    tmp_path, capsys, monkeypatch, workflow
):
    """Quoting does not make an expansion static; the repository name is unknown."""
    root = _prepare(tmp_path, monkeypatch, workflow)
    plan = _written(root, capsys)
    assert _clones(plan) == []
    assert not [d for d in plan["diagnostics"] if d["code"] == "policy_node_mismatch"]
    assert len(_unsupported(plan)) == 1
    assert cli.main(["--check", "--root", str(root)]) == 1


def test_a_quoted_dynamic_target_does_not_hide_a_separate_static_clone(
    tmp_path, capsys, monkeypatch
):
    root = _prepare(tmp_path, monkeypatch, WORKFLOW_EXPR_QUOTED_DYNAMIC_THEN_STATIC)
    plan = _written(root, capsys)
    assert [
        (e["from"], e["to"], e["purpose"], e["declared"]["url"]) for e in _clones(plan)
    ] == [("python-docx", "ooxml-core", "workflow_clone", CORE)]
    assert len(_unsupported(plan)) == 1
    assert cli.main(["--check", "--root", str(root)]) == 1


@pytest.mark.parametrize(
    "workflow",
    [WORKFLOW_EXPR_FORMAT_STRIP, WORKFLOW_EXPR_FORMAT_KEEP],
    ids=["strip-chomping", "keep-chomping"],
)
def test_an_expression_before_a_clone_does_not_swallow_it(tmp_path, capsys, monkeypatch, workflow):
    """The trailing newline changes bash error recovery, not the dependency."""
    root = _prepare(tmp_path, monkeypatch, workflow)
    _assert_one_corpus_edge(_written(root, capsys))
    _assert_clean_strict(root, capsys)


def test_an_escaped_url_is_decoded_before_matching_a_node(tmp_path, capsys, monkeypatch):
    """``ooxml\\-native-corpus`` is the same repository as ``ooxml-native-corpus``."""
    root = _prepare(tmp_path, monkeypatch, WORKFLOW_EXPR_ESCAPED)
    _assert_one_corpus_edge(_written(root, capsys))
    _assert_clean_strict(root, capsys)


@pytest.mark.parametrize(
    "workflow",
    [WORKFLOW_EXPR_VAR_REPO, WORKFLOW_EXPR_ACTIONS_REPO],
    ids=["shell-variable", "actions-expression"],
)
def test_a_dynamic_clone_target_is_reported_not_guessed(tmp_path, capsys, monkeypatch, workflow):
    """An unresolved repository argument is a structural error, never a fake node."""
    root = _prepare(tmp_path, monkeypatch, workflow)
    plan = _written(root, capsys)
    assert _clones(plan) == []
    assert not [d for d in plan["diagnostics"] if d["code"] == "policy_node_mismatch"]
    reported = _unsupported(plan)
    assert len(reported) == 1
    assert "git clone target is not statically known" in reported[0]["detail"]
    assert reported[0]["where"].startswith(f"{WORKFLOW_RELPATH}:")
    assert reported[0]["level"] == "error"
    assert cli.main(["--check", "--root", str(root)]) == 1
    assert "unsupported_workflow" in capsys.readouterr().out


def test_a_dynamic_target_does_not_hide_a_separate_static_clone(tmp_path, capsys, monkeypatch):
    """The static edge survives; the run is not skipped wholesale."""
    root = _prepare(tmp_path, monkeypatch, WORKFLOW_EXPR_VAR_REPO_THEN_STATIC)
    plan = _written(root, capsys)
    assert [
        (e["from"], e["to"], e["purpose"], e["declared"]["url"]) for e in _clones(plan)
    ] == [("python-docx", "ooxml-core", "workflow_clone", CORE)]
    assert "python-docx" in plan["graphs"]["impact"]["ooxml-core"]["reaches"]
    assert len(_unsupported(plan)) == 1
    assert cli.main(["--check", "--root", str(root)]) == 1


def test_unreadable_shell_is_reported_instead_of_read_as_no_dependency(tmp_path, capsys, monkeypatch):
    root = _prepare(tmp_path, monkeypatch, WORKFLOW_EXPR_UNREADABLE)
    plan = _written(root, capsys)
    assert _clones(plan) == []
    assert len(_unsupported(plan)) == 1
    assert "could not be read as shell" in _unsupported(plan)[0]["detail"]
    assert cli.main(["--check", "--root", str(root)]) == 1


@pytest.mark.parametrize(
    "workflow",
    [WORKFLOW_EXPR_QUOTED_THEN_CLONE, WORKFLOW_EXPR_MULTILINE_THEN_CLONE],
    ids=["quoted-semicolon", "multiline-quote"],
)
def test_the_earlier_mixed_cases_still_hold(tmp_path, capsys, monkeypatch, workflow):
    """A quoted example is not a clone; the real clone on the next line still is."""
    root = _prepare(tmp_path, monkeypatch, workflow)
    _assert_one_corpus_edge(_written(root, capsys))
    _assert_clean_strict(root, capsys)


def test_a_run_body_may_spell_the_placeholder(tmp_path, capsys, monkeypatch):
    """The mask must never collide with real text: no crash, no invented diagnostic."""
    root = _prepare(tmp_path, monkeypatch, WORKFLOW_EXPR_LITERAL_MARKER)
    plan = _written(root, capsys)
    assert _clones(plan) == []
    assert _unsupported(plan) == []
    _assert_clean_strict(root, capsys)


def test_a_placeholder_collision_does_not_break_a_real_expression(tmp_path, capsys, monkeypatch):
    """With the prefix bumped, the real expression still restores to its own text."""
    root = _prepare(tmp_path, monkeypatch, WORKFLOW_EXPR_MARKER_COLLISION)
    plan = _written(root, capsys)
    assert _clones(plan) == []
    reported = _unsupported(plan)
    assert len(reported) == 1
    assert "${{ inputs.repo }}" in reported[0]["detail"]
    assert "ooxml_actions_expr" not in reported[0]["detail"]
    assert cli.main(["--check", "--root", str(root)]) == 1