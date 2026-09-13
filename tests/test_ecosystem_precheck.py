"""Clean-interpreter acceptance for the dependency precheck.

A missing ``packaging``/``PyYAML``/``tree-sitter``/``tree-sitter-bash`` must
produce a preparation command, never an ``ImportError`` traceback. These run the
CLI in a *real* subprocess with an interpreter that genuinely cannot import any
of them: stubbing ``cli.main`` would prove nothing about the import chain.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from ecosystem_fixtures import REPO_ROOT, build_workspace, write

PLAN_RELPATH = "ooxml-stack/ci/ecosystem-plan.json"
SCAN_RELPATH = "ooxml-stack/ci/reports/scan.json"


@pytest.fixture(scope="module")
def bare_python(tmp_path_factory) -> pathlib.Path:
    """An interpreter that really cannot import ``yaml`` or ``packaging``."""
    venv = tmp_path_factory.mktemp("bare") / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True)
    python = venv / "bin/python"
    probe = subprocess.run(
        [
            str(python),
            "-c",
            "import importlib.util as u; print(u.find_spec('yaml'), u.find_spec('packaging'))",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert probe.stdout.split() == ["None", "None"], f"interpreter is not clean: {probe.stdout}"
    return python


def _run(python: pathlib.Path, *args: str, cwd: pathlib.Path | None = None):
    return subprocess.run(
        [str(python), "-m", "scripts.ooxml_ci", *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
    )


def test_a_clean_interpreter_refuses_with_a_preparation_command(bare_python, tmp_path):
    root = build_workspace(tmp_path)
    result = _run(bare_python, "--check", "--root", str(root))
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "dependency error" in result.stderr
    for package in ("PyYAML", "packaging", "tree-sitter", "tree-sitter-bash"):
        assert package in result.stderr, f"{package} missing from the report"
    assert "make ecosystem-inventory-deps" in result.stderr
    assert not (root / PLAN_RELPATH).exists()
    assert not (root / SCAN_RELPATH).exists()


def test_a_clean_interpreter_write_refuses_too(bare_python, tmp_path):
    root = build_workspace(tmp_path)
    result = _run(bare_python, "--write", "--root", str(root))
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert not (root / PLAN_RELPATH).exists()
    assert not (root / SCAN_RELPATH).exists()


def test_a_clean_interpreter_leaves_existing_artifacts_untouched(bare_python, tmp_path):
    root = build_workspace(tmp_path)
    write(root / PLAN_RELPATH, '{"sentinel": "plan"}\n')
    write(root / SCAN_RELPATH, '{"sentinel": "scan"}\n')
    for mode in ("--write", "--check"):
        result = _run(bare_python, mode, "--root", str(root))
        assert result.returncode == 2
    assert (root / PLAN_RELPATH).read_text(encoding="utf-8") == '{"sentinel": "plan"}\n'
    assert (root / SCAN_RELPATH).read_text(encoding="utf-8") == '{"sentinel": "scan"}\n'


def test_help_needs_neither_third_party_packages_nor_a_workspace(bare_python, tmp_path):
    """``--help`` must work from a directory that is not a workspace at all."""
    assert not (tmp_path / "ooxml-stack").exists()
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    result = subprocess.run(
        [str(bare_python), "-m", "scripts.ooxml_ci", "--help"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()
    assert result.stderr == ""


def test_the_precheck_reads_only_the_declaration(bare_python, tmp_path):
    """A malformed declaration is reported before any ecosystem input is touched."""
    root = build_workspace(tmp_path)
    write(root / "ooxml-stack/ci/ecosystem-inventory-requirements.txt", "# empty\n")
    (root / "ooxml-core/pyproject.toml").write_text("this is not toml {{{\n", encoding="utf-8")
    result = _run(bare_python, "--write", "--root", str(root))
    assert result.returncode == 2
    assert "dependency error" in result.stderr
    assert "incomplete" in result.stderr
    assert not (root / PLAN_RELPATH).exists()


def test_the_precheck_does_not_swallow_other_failures(bare_python, tmp_path):
    """Only a declaration problem may be reported as a dependency problem."""
    root = build_workspace(tmp_path)
    write(root / "ooxml-stack/ci/ecosystem-inventory-requirements.txt", "# empty\n")
    result = _run(bare_python, "--write", "--root", str(root))
    assert result.returncode == 2
    assert "incomplete" in result.stderr
    assert "Traceback" not in result.stderr


def test_pythonpath_is_not_needed_when_running_from_the_repo(bare_python, tmp_path):
    """The documented invocation works from the host repo without extra env."""
    root = build_workspace(tmp_path)
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [str(bare_python), "-m", "scripts.ooxml_ci", "--check", "--root", str(root)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 2
    assert "dependency error" in result.stderr