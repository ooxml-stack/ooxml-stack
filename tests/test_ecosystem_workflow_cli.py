"""CLI acceptance for workflow-derived facts: clone edges and structured fields.

``--write`` records what it could read; a structure it could not read must make
the following ``--check`` fail rather than pass silently.
"""

from __future__ import annotations

import json

import pytest

from ecosystem_fixtures import build_workspace, resolvable_for, seal, write
from ecosystem_workflows import (
    WORKFLOW_CLONE_FOLDED,
    WORKFLOW_CLONE_LITERAL,
    WORKFLOW_CLONE_MULTILINE_QUOTED_MIXED,
    WORKFLOW_CLONE_QUOTED_MIXED,
    WORKFLOW_CLONE_SINGLE,
    WORKFLOW_MATRIX_CUSTOM_TAG,
    WORKFLOW_MATRIX_DUPLICATE_KEY,
)
from scripts.ooxml_ci import cli

PLAN_RELPATH = "ooxml-stack/ci/ecosystem-plan.json"


def _no_skew(root, heads):
    """Align python-pptx with python-docx so ``--strict`` has no warning to upgrade."""
    write(
        root / "python-pptx/pyproject.toml",
        '[project]\nname = "python-pptx"\nversion = "1.0.2"\n'
        'dependencies = ["ooxml-core @ git+https://github.com/ooxml-stack/ooxml-core.git@v0.6.0"]\n',
    )
    write(
        root / "python-pptx/uv.lock",
        "[[package]]\n"
        'name = "ooxml-core"\n'
        'version = "0.6.0"\n'
        f'source = {{ git = "https://github.com/ooxml-stack/ooxml-core.git?tag=v0.6.0#{heads["ooxml-core"]}" }}\n',
    )


@pytest.mark.parametrize(
    "workflow",
    [WORKFLOW_MATRIX_DUPLICATE_KEY, WORKFLOW_MATRIX_CUSTOM_TAG],
    ids=["repeated-key", "custom-tag"],
)
def test_an_unreadable_matrix_is_written_then_fails_check(tmp_path, capsys, monkeypatch, workflow):
    """``--write`` keeps the diagnostic; both ``--check`` modes must then fail."""
    root = build_workspace(tmp_path)
    resolvable_for(monkeypatch, seal(root))
    write(root / "ooxml-core/.github/workflows/full.yml", workflow)
    assert cli.main(["--write", "--root", str(root)]) == 0
    capsys.readouterr()
    plan = json.loads((root / PLAN_RELPATH).read_text(encoding="utf-8"))
    assert any(item["code"] == "unsupported_workflow" for item in plan["diagnostics"])
    assert plan["full"]["ooxml-core"]["jobs"][0]["matrix"] == {}
    assert cli.main(["--check", "--root", str(root)]) == 1
    assert "unsupported_workflow" in capsys.readouterr().out
    assert cli.main(["--check", "--strict", "--root", str(root)]) == 1
    assert "unsupported_workflow" in capsys.readouterr().out


@pytest.mark.parametrize(
    "workflow",
    [WORKFLOW_CLONE_SINGLE, WORKFLOW_CLONE_LITERAL, WORKFLOW_CLONE_FOLDED],
    ids=["single-line", "literal-block", "folded-block"],
)
def test_a_clone_only_workflow_passes_check_strict(tmp_path, capsys, monkeypatch, workflow):
    """A no-drift fixture must pass ``--check --strict`` however the clone is written."""
    root = build_workspace(tmp_path)
    heads = seal(root)
    _no_skew(root, heads)
    resolvable_for(monkeypatch, heads)
    write(root / "python-docx/.github/workflows/ci.yml", workflow)
    assert cli.main(["--write", "--root", str(root)]) == 0
    capsys.readouterr()
    assert cli.main(["--check", "--strict", "--root", str(root)]) == 0
    assert "result        : ok" in capsys.readouterr().out


@pytest.mark.parametrize(
    "workflow",
    [WORKFLOW_CLONE_QUOTED_MIXED, WORKFLOW_CLONE_MULTILINE_QUOTED_MIXED],
    ids=["quoted-semicolon", "multiline-quote"],
)
def test_a_quoted_clone_does_not_disturb_a_no_drift_check(tmp_path, capsys, monkeypatch, workflow):
    """A quoted clone must leave ``--check --strict`` clean and add no fake edge."""
    root = build_workspace(tmp_path)
    heads = seal(root)
    _no_skew(root, heads)
    resolvable_for(monkeypatch, heads)
    write(root / "python-docx/.github/workflows/ci.yml", workflow)
    assert cli.main(["--write", "--root", str(root)]) == 0
    capsys.readouterr()
    plan = json.loads((root / PLAN_RELPATH).read_text(encoding="utf-8"))
    clones = [e for e in plan["edges"] if e.get("purpose") == "workflow_clone"]
    assert [(e["from"], e["to"]) for e in clones] == [("python-docx", "ooxml-native-corpus")]
    assert not [item for item in plan["diagnostics"] if item["code"] == "policy_node_mismatch"]
    assert cli.main(["--check", "--strict", "--root", str(root)]) == 0
    assert "result        : ok" in capsys.readouterr().out


def test_a_malformed_policy_is_an_input_error_not_a_dependency_error(tmp_path, capsys):
    """Only a declaration problem may be reported as a dependency problem."""
    root = build_workspace(tmp_path)
    write(root / "ooxml-stack/ci/ecosystem-policy.json", "{ not json")
    assert cli.main(["--write", "--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert "input error" in err
    assert "dependency error" not in err


REMOTE_CLONE_FORMS = [
    ("https", "https://github.com/ooxml-stack/ooxml-native-corpus.git"),
    ("git-protocol", "git://github.com/ooxml-stack/ooxml-native-corpus.git"),
    ("upper-case-scheme", "HTTPS://github.com/ooxml-stack/ooxml-native-corpus.git"),
    ("ssh", "ssh://git@github.com/ooxml-stack/ooxml-native-corpus.git"),
    ("scp", "git@github.com:ooxml-stack/ooxml-native-corpus.git"),
    ("trailing-slash", "https://github.com/ooxml-stack/ooxml-native-corpus.git/"),
]


@pytest.mark.parametrize(
    "url", [url for _, url in REMOTE_CLONE_FORMS], ids=[n for n, _ in REMOTE_CLONE_FORMS]
)
def test_every_remote_form_becomes_a_real_edge(tmp_path, capsys, monkeypatch, url):
    """A resolvable remote URL must produce the edge, never a silent empty result."""
    root = build_workspace(tmp_path)
    heads = seal(root)
    _no_skew(root, heads)
    resolvable_for(monkeypatch, heads)
    write(
        root / "python-docx/.github/workflows/ci.yml",
        f"name: ci\non: [push]\njobs:\n  ci:\n    runs-on: ubuntu-latest\n"
        f"    steps:\n      - run: |-\n          git clone {url}\n",
    )
    assert cli.main(["--write", "--root", str(root)]) == 0
    capsys.readouterr()
    plan = json.loads((root / PLAN_RELPATH).read_text(encoding="utf-8"))
    clones = [e for e in plan["edges"] if e.get("purpose") == "workflow_clone"]
    assert [(e["from"], e["to"], e["kind"], e["declared"]["url"]) for e in clones] == [
        ("python-docx", "ooxml-native-corpus", "ci", url)
    ]
    assert "python-docx" in plan["graphs"]["impact"]["ooxml-native-corpus"]["reaches"]
    assert not [item for item in plan["diagnostics"] if item["code"] == "policy_node_mismatch"]
    assert not [item for item in plan["diagnostics"] if item["code"] == "unsupported_workflow"]
    assert cli.main(["--check", "--strict", "--root", str(root)]) == 0
    assert "result        : ok" in capsys.readouterr().out