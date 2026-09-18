"""Input-side acceptance tests: discovery, input selection and byte parsers."""

from __future__ import annotations

import json

import pytest

from ecosystem_fixtures import (
    CORE_SHA,
    NODES,
    build,
    build_workspace,
    make_policy,
    write,
)
from scripts.ooxml_ci import inputs, parsers


# ------------------------------------------------------------------ discovery


def test_find_root_locates_the_workspace(tmp_path):
    root = build_workspace(tmp_path)
    assert inputs.find_root(root / "python-docx") == root


def test_find_root_rejects_a_directory_without_core(tmp_path):
    (tmp_path / "ooxml-stack").mkdir()
    with pytest.raises(inputs.InputError):
        inputs.find_root(tmp_path)


def test_load_policy_rejects_duplicate_keys(tmp_path):
    root = build_workspace(tmp_path, make_policy(nodes=[NODES[0], NODES[0]]))
    with pytest.raises(inputs.InputError, match="duplicate"):
        inputs.load_policy(root)


def test_load_policy_requires_the_host_node(tmp_path):
    root = build_workspace(tmp_path, make_policy(nodes=NODES[1:]))
    with pytest.raises(inputs.InputError, match="host node"):
        inputs.load_policy(root)


def test_load_policy_requires_schema_version(tmp_path):
    root = build_workspace(tmp_path, make_policy(schema_version=99))
    with pytest.raises(inputs.InputError, match="schema_version"):
        inputs.load_policy(root)


# --------------------------------------------------------------------- inputs


def test_missing_declared_input_is_a_structural_error(tmp_path):
    root = build_workspace(tmp_path)
    (root / "ooxml-core/ci/environment.json").unlink()
    plan = build(root)
    codes = {(item["code"], item["where"]) for item in plan["diagnostics"]}
    assert ("missing_input", "ooxml-core/ci/environment.json") in codes


def test_missing_snapshot_file_does_not_silently_drop_edges(tmp_path):
    root = build_workspace(tmp_path)
    (root / "ooxml-core/ci/environment.json").unlink()
    plan = build(root)
    assert not [edge for edge in plan["edges"] if edge.get("purpose") == "engine_ci_snapshot"]
    assert any(item["code"] == "missing_input" for item in plan["diagnostics"])


def test_dynamic_version_source_is_a_selected_input(tmp_path):
    root = build_workspace(tmp_path)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\n'
        '[tool.setuptools.dynamic]\nversion = {attr = "docx.__version__"}\n',
    )
    write(root / "python-docx/src/docx/__init__.py", '__version__ = "1.2.0"\n')
    policy = inputs.load_policy(root)
    selected, _ = inputs.select_inputs(root, policy)
    assert "python-docx/src/docx/__init__.py" in selected


def test_plan_changes_when_only_the_dynamic_version_source_changes(tmp_path):
    root = build_workspace(tmp_path)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\n'
        '[tool.setuptools.dynamic]\nversion = {attr = "docx.__version__"}\n',
    )
    write(root / "python-docx/src/docx/__init__.py", '__version__ = "1.2.0"\n')
    before = build(root)
    write(root / "python-docx/src/docx/__init__.py", '__version__ = "1.2.1"\n')
    after = build(root)
    assert before["inputs_digest"] != after["inputs_digest"]
    docx_before = next(n for n in before["nodes"] if n["key"] == "python-docx")
    docx_after = next(n for n in after["nodes"] if n["key"] == "python-docx")
    assert docx_before["version"] == "1.2.0"
    assert docx_after["version"] == "1.2.1"


def test_inputs_digest_excludes_the_plan_itself(tmp_path):
    root = build_workspace(tmp_path)
    policy = inputs.load_policy(root)
    before, _ = inputs.select_inputs(root, policy)
    write(root / "ooxml-stack/ci/ecosystem-plan.json", '{"stale": true}\n')
    after, _ = inputs.select_inputs(root, policy)
    assert inputs.inputs_digest(inputs.input_manifest(before)) == inputs.inputs_digest(
        inputs.input_manifest(after)
    )


# -------------------------------------------------------------------- parsers


def test_project_version_reads_static_version(tmp_path):
    root = build_workspace(tmp_path)
    assert parsers.parse_project_version(
        (root / "ooxml-core/pyproject.toml").read_bytes(), "ooxml-core", None
    ) == ("0.6.0", "pyproject.toml#project.version")


def test_project_version_follows_dynamic_attr():
    pyproject = b'[project]\nname = "x"\n[tool.setuptools.dynamic]\nversion = {attr = "xlsx.__version__"}\n'
    assert parsers.parse_project_version(pyproject, "python-xlsx", b'__version__ = "0.3.51"\n') == (
        "0.3.51",
        "src/xlsx/__init__.py#__version__",
    )


def test_parse_uv_lock_records_git_packages(tmp_path):
    root = build_workspace(tmp_path)
    lock = parsers.parse_uv_lock((root / "python-docx/uv.lock").read_bytes())
    assert lock["ooxml-core"]["version"] == "0.6.0"
    assert lock["ooxml-core"]["ref"] == "v0.6.0"
    assert lock["ooxml-core"]["expected_commit"] == CORE_SHA



def test_policy_json_round_trips_through_canonical_json(tmp_path):
    root = build_workspace(tmp_path)
    policy = inputs.load_policy(root)
    assert json.loads(inputs.canonical_json(policy)) == policy