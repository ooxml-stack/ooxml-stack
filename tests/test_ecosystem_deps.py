"""Pinned tool environment: the declaration, the gate and the scan observation."""

from __future__ import annotations

import json

import pytest

from ecosystem_fixtures import (
    REPO_ROOT,
    REQUIREMENTS_TEXT,
    build,
    build_workspace,
    resolvable_for,
    seal,
    write,
)
from scripts.ooxml_ci import cli, deps, inputs, scan as scan_mod

# The real declaration with one line perturbed, so each case tests one defect.
WRONG_PACKAGING = REQUIREMENTS_TEXT.replace("packaging==26.0", "packaging==21.3")


def test_the_declaration_pins_exact_versions():
    pinned = deps.parse_requirements(REQUIREMENTS_TEXT)
    assert set(pinned) == {"packaging", "PyYAML", "tree-sitter", "tree-sitter-bash"}
    assert all(version[0].isdigit() for version in pinned.values())


def test_an_unpinned_requirement_is_a_declaration_error():
    with pytest.raises(deps.DependencyError, match="name==version"):
        deps.parse_requirements("packaging>=24\n")


def test_the_running_interpreter_matches_the_declaration(tmp_path):
    report = deps.check(build_workspace(tmp_path))
    assert report["problems"] == []
    assert report["pinned"] == report["installed"]


def test_a_missing_declaration_is_reported(tmp_path):
    root = build_workspace(tmp_path)
    (root / "ooxml-stack/ci/ecosystem-inventory-requirements.txt").unlink()
    assert any("absent" in problem for problem in deps.check(root)["problems"])


def test_a_version_mismatch_is_reported(tmp_path):
    root = build_workspace(tmp_path)
    write(root / "ooxml-stack/ci/ecosystem-inventory-requirements.txt", WRONG_PACKAGING)
    problems = deps.check(root)["problems"]
    assert problems == ["packaging==26.0 is installed but 21.3 is declared"]


def test_the_declaration_is_a_plan_input(tmp_path):
    plan = build(build_workspace(tmp_path))
    assert "ooxml-stack/ci/ecosystem-inventory-requirements.txt" in plan["inputs"]


def test_changing_the_declaration_changes_the_digest(tmp_path):
    """A different pinned toolchain must not be able to reuse a committed plan."""
    first = build_workspace(tmp_path / "one")
    second = build_workspace(tmp_path / "two")
    before = build(first)["inputs_digest"]
    write(second / "ooxml-stack/ci/ecosystem-inventory-requirements.txt", WRONG_PACKAGING)
    assert build(second)["inputs_digest"] != before


def test_cli_refuses_to_run_without_the_pinned_environment(tmp_path, capsys):
    root = build_workspace(tmp_path)
    write(root / "ooxml-stack/ci/ecosystem-inventory-requirements.txt", WRONG_PACKAGING)
    assert cli.main(["--write", "--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert "dependency error" in err
    assert "make ecosystem-inventory-deps" in err
    assert not (root / "ooxml-stack/ci/ecosystem-plan.json").exists()


def test_cli_does_not_overwrite_an_existing_plan_when_dependencies_are_wrong(tmp_path, capsys):
    root = build_workspace(tmp_path)
    plan = root / "ooxml-stack/ci/ecosystem-plan.json"
    write(plan, '{"sentinel": true}\n')
    write(root / "ooxml-stack/ci/ecosystem-inventory-requirements.txt", WRONG_PACKAGING)
    assert cli.main(["--write", "--root", str(root)]) == 2
    capsys.readouterr()
    assert plan.read_text(encoding="utf-8") == '{"sentinel": true}\n'


def test_cli_check_also_refuses_without_the_pinned_environment(tmp_path, capsys):
    root = build_workspace(tmp_path)
    write(root / "ooxml-stack/ci/ecosystem-inventory-requirements.txt", WRONG_PACKAGING)
    assert cli.main(["--check", "--root", str(root)]) == 2
    assert "dependency error" in capsys.readouterr().err


def test_the_scan_records_the_environment_and_the_plan_does_not(tmp_path, monkeypatch):
    root = build_workspace(tmp_path)
    resolvable_for(monkeypatch, seal(root))
    policy = inputs.load_policy(root)
    plan = build(root)
    report = scan_mod.scan(root, policy, plan, offline=False)
    assert report["environment"]["packages"]["packaging"] == "26.0"
    assert report["environment"]["packages"]["PyYAML"] == "6.0.3"
    assert report["environment"]["python"].startswith("3.")
    assert "environment" not in plan


def test_the_scan_is_not_byte_stable_but_the_plan_is(tmp_path, monkeypatch):
    """Environment observations belong to the scan; the plan must not carry them."""
    root = build_workspace(tmp_path)
    resolvable_for(monkeypatch, seal(root))
    policy = inputs.load_policy(root)
    first = build(root)
    second = build(root)
    assert inputs.canonical_json(first) == inputs.canonical_json(second)
    report = scan_mod.scan(root, policy, first, offline=False)
    assert json.dumps(report["environment"], sort_keys=True) != inputs.canonical_json(first)


# ------------------------------------------------- declaration completeness


INCOMPLETE_DECLARATIONS = [
    "",
    "# nothing but a comment\n",
    "PyYAML==6.0.3\ntree-sitter==0.26.0\ntree-sitter-bash==0.25.1\n",  # packaging missing
    "packaging==26.0\ntree-sitter==0.26.0\ntree-sitter-bash==0.25.1\n",  # PyYAML missing
    "packaging==26.0\nPyYAML==6.0.3\n",  # the shell parser missing
    REQUIREMENTS_TEXT + "PyYAML==6.0.3\n",  # repeated
    REQUIREMENTS_TEXT + "pyyaml==6.0.2\n",  # same distribution, two spellings
    REQUIREMENTS_TEXT + "requests==2.31.0\n",  # unknown package
    "packaging>=26.0\nPyYAML==6.0.3\ntree-sitter==0.26.0\ntree-sitter-bash==0.25.1\n",
    "packaging===26.0\nPyYAML==6.0.3\ntree-sitter==0.26.0\ntree-sitter-bash==0.25.1\n",
    "packaging==26.0\nPyYAML==6.0.3\ntree-sitter==0.26.0\ntree-sitter-bash==0.25.1\n-r other.txt\n",
]


@pytest.mark.parametrize("text", INCOMPLETE_DECLARATIONS, ids=range(len(INCOMPLETE_DECLARATIONS)))
def test_an_incomplete_declaration_is_never_read_as_no_problems(tmp_path, text):
    root = build_workspace(tmp_path)
    write(root / "ooxml-stack/ci/ecosystem-inventory-requirements.txt", text)
    report = deps.check(root)
    assert report["problems"], f"{text!r} was accepted"
    assert report["pinned"] == {}


def test_a_missing_required_package_names_what_is_missing():
    with pytest.raises(deps.DependencyError, match="incomplete.*packaging"):
        deps.parse_requirements("PyYAML==6.0.3\ntree-sitter==0.26.0\ntree-sitter-bash==0.25.1\n")


def test_an_alias_duplicate_is_rejected_not_merged():
    """``PyYAML`` and ``pyyaml`` are one distribution, so two pins are a conflict."""
    with pytest.raises(deps.DependencyError, match="duplicate declaration for PyYAML"):
        deps.parse_requirements(REQUIREMENTS_TEXT + "pyyaml==6.0.2\n")


def test_a_single_alias_spelling_is_accepted_and_canonicalized():
    """One spelling of a distribution is fine; the canonical name is what is compared."""
    text = "packaging==26.0\npyyaml==6.0.3\ntree-sitter==0.26.0\ntree-sitter-bash==0.25.1\n"
    assert deps.parse_requirements(text) == {
        "packaging": "26.0",
        "PyYAML": "6.0.3",
        "tree-sitter": "0.26.0",
        "tree-sitter-bash": "0.25.1",
    }


def test_an_unknown_package_is_rejected():
    with pytest.raises(deps.DependencyError, match="unsupported dependency 'requests'"):
        deps.parse_requirements(REQUIREMENTS_TEXT + "requests==2.31.0\n")


def test_the_prepare_command_runs_from_the_workspace_root():
    """The printed command must actually work: the host repo holds both inputs."""
    command = deps.prepare_command()
    assert command == "cd ooxml-stack && make ecosystem-inventory-deps"
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "ecosystem-inventory-deps:" in makefile
    assert (REPO_ROOT / "ci/ecosystem-inventory-test-requirements.txt").is_file()


@pytest.fixture
def committed(tmp_path, monkeypatch):
    """A workspace with a written plan and scan, and a resolvable remote."""
    root = build_workspace(tmp_path)
    resolvable_for(monkeypatch, seal(root))
    assert cli.main(["--write", "--root", str(root)]) == 0
    return root


def _artifacts(root):
    return {
        name: (root / "ooxml-stack" / name).read_bytes()
        for name in ("ci/ecosystem-plan.json", "ci/reports/scan.json")
    }


@pytest.mark.parametrize("text", ["", "PyYAML==6.0.3\n"], ids=["empty", "missing-packaging"])
def test_cli_blocks_an_incomplete_declaration_and_leaves_both_artifacts_alone(
    committed, capsys, text
):
    before = _artifacts(committed)
    write(committed / "ooxml-stack/ci/ecosystem-inventory-requirements.txt", text)
    capsys.readouterr()
    assert cli.main(["--write", "--root", str(committed)]) == 2
    assert cli.main(["--check", "--strict", "--root", str(committed)]) == 2
    err = capsys.readouterr().err
    assert "dependency error" in err
    assert "make ecosystem-inventory-deps" in err
    assert _artifacts(committed) == before


def test_a_blocked_gate_creates_no_artifacts(tmp_path, capsys, monkeypatch):
    """The precheck runs before the scan, so a refusal must not leave a scan behind."""
    root = build_workspace(tmp_path)
    resolvable_for(monkeypatch, seal(root))
    write(root / "ooxml-stack/ci/ecosystem-inventory-requirements.txt", "")
    assert cli.main(["--write", "--root", str(root)]) == 2
    capsys.readouterr()
    assert not (root / "ooxml-stack/ci/ecosystem-plan.json").exists()
    assert not (root / "ooxml-stack/ci/reports/scan.json").exists()