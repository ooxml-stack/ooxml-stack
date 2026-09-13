"""Plan-side acceptance tests: CI edges, graphs, full bindings and plan shape."""

from __future__ import annotations

import pytest

from ecosystem_fixtures import build, build_workspace, make_policy, write
from ecosystem_workflows import (
    WORKFLOW_CLONE_FOLDED,
    WORKFLOW_CLONE_LITERAL,
    WORKFLOW_CLONE_MULTILINE_QUOTED_MIXED,
    WORKFLOW_CLONE_QUOTED_DECLARED,
    WORKFLOW_CLONE_QUOTED_MIXED,
    WORKFLOW_CLONE_SINGLE,
    WORKFLOW_DOCX_THIRD_PARTY,
    WORKFLOW_DOCX_UNKNOWN,
    WORKFLOW_ENV_NESTED,
    WORKFLOW_FULL_ENV,
    WORKFLOW_MENTIONS_CLONE,
)
from scripts.ooxml_ci import inputs


# ------------------------------------------------------------------ workflows


def test_workflow_uses_creates_a_ci_edge(tmp_path):
    plan = build(build_workspace(tmp_path))
    edge = next(
        e for e in plan["edges"] if e["from"] == "python-docx" and e.get("purpose") == "workflow_uses"
    )
    assert edge["to"] == "ooxml-stack"
    assert edge["kind"] == "ci"
    assert edge["declared"]["ref_raw"] == "v1.0.0"
    assert edge["declared"]["url"] == "https://github.com/ooxml-stack/ooxml-stack"


def test_workflow_uses_an_undeclared_node_is_a_structural_error(tmp_path):
    root = build_workspace(tmp_path)
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_DOCX_UNKNOWN)
    plan = build(root)
    assert any(
        item["code"] == "policy_node_mismatch" and "ooxml-new" in item["detail"]
        for item in plan["diagnostics"]
    )
    assert not [e for e in plan["edges"] if e.get("purpose") == "workflow_uses"]


def test_third_party_actions_are_not_policy_nodes(tmp_path):
    root = build_workspace(tmp_path)
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_DOCX_THIRD_PARTY)
    plan = build(root)
    assert not [item for item in plan["diagnostics"] if item["code"] == "policy_node_mismatch"]


def test_workflow_clone_creates_a_ci_edge(tmp_path):
    plan = build(build_workspace(tmp_path))
    edge = next(
        e for e in plan["edges"] if e["from"] == "python-docx" and e.get("purpose") == "workflow_clone"
    )
    assert edge["to"] == "ooxml-native-corpus"


def _clone_edges(root):
    plan = build(root)
    return plan, [e for e in plan["edges"] if e.get("purpose") == "workflow_clone"]


def test_a_folded_clone_creates_the_ci_edge(tmp_path):
    """A folded ``git clone`` is one command, so it must produce the same edge."""
    root = build_workspace(tmp_path)
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_CLONE_FOLDED)
    plan, edges = _clone_edges(root)
    assert len(edges) == 1
    assert (edges[0]["from"], edges[0]["to"], edges[0]["kind"]) == (
        "python-docx",
        "ooxml-native-corpus",
        "ci",
    )
    assert not [item for item in plan["diagnostics"] if item["code"] == "policy_node_mismatch"]


def test_the_three_clone_writings_produce_the_same_edge_semantics(tmp_path):
    shapes = []
    for index, workflow in enumerate(
        (WORKFLOW_CLONE_SINGLE, WORKFLOW_CLONE_LITERAL, WORKFLOW_CLONE_FOLDED)
    ):
        root = build_workspace(tmp_path / str(index))
        write(root / "python-docx/.github/workflows/ci.yml", workflow)
        _, edges = _clone_edges(root)
        shapes.append(
            sorted((e["from"], e["to"], e["kind"], e.get("purpose")) for e in edges)
        )
    assert shapes[0] == shapes[1] == shapes[2]
    assert shapes[0] == [("python-docx", "ooxml-native-corpus", "ci", "workflow_clone")]


def test_a_folded_clone_puts_the_consumer_in_the_target_impact_set(tmp_path):
    root = build_workspace(tmp_path)
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_CLONE_FOLDED)
    plan = build(root)
    reaches = set(plan["graphs"]["impact"]["ooxml-native-corpus"]["reaches"])
    assert "python-docx" in reaches


def test_a_mentioned_clone_produces_no_edge_and_no_mismatch(tmp_path):
    """The next step's ``name`` must not be read as a command."""
    root = build_workspace(tmp_path)
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_MENTIONS_CLONE)
    plan, edges = _clone_edges(root)
    assert edges == []
    assert not [item for item in plan["diagnostics"] if item["code"] == "policy_node_mismatch"]


@pytest.mark.parametrize(
    "workflow",
    [WORKFLOW_CLONE_QUOTED_MIXED, WORKFLOW_CLONE_MULTILINE_QUOTED_MIXED],
    ids=["quoted-semicolon", "multiline-quote"],
)
def test_a_quoted_clone_is_neither_an_edge_nor_a_mismatch(tmp_path, workflow):
    """Quoted text is echo output: no edge into the graph, and no undeclared-node alarm."""
    root = build_workspace(tmp_path)
    write(root / "python-docx/.github/workflows/ci.yml", workflow)
    plan, edges = _clone_edges(root)
    assert [(e["from"], e["to"], e["kind"]) for e in edges] == [
        ("python-docx", "ooxml-native-corpus", "ci")
    ]
    assert not [item for item in plan["diagnostics"] if item["code"] == "policy_node_mismatch"]
    reaches = set(plan["graphs"]["impact"]["ooxml-native-corpus"]["reaches"])
    assert "python-docx" in reaches


def test_a_quoted_clone_of_a_declared_node_adds_no_edge(tmp_path):
    """The fake target is a real policy node, so only the grammar keeps it out."""
    root = build_workspace(tmp_path)
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_CLONE_QUOTED_DECLARED)
    plan, edges = _clone_edges(root)
    assert [(e["from"], e["to"], e["kind"]) for e in edges] == [
        ("python-docx", "ooxml-native-corpus", "ci")
    ]
    assert not [e for e in edges if e["to"] == "ooxml-core"]
    assert not [item for item in plan["diagnostics"] if item["code"] == "policy_node_mismatch"]


def test_impact_graph_reaches_workflow_consumers(tmp_path):
    """Repos that reference the host workflow must appear in the host's impact set."""
    plan = build(build_workspace(tmp_path))
    reaches = set(plan["graphs"]["impact"]["ooxml-stack"]["reaches"])
    assert {"ooxml-stack", "python-docx"} <= reaches


def test_impact_graph_reaches_the_snapshot_owner(tmp_path):
    plan = build(build_workspace(tmp_path))
    reaches = set(plan["graphs"]["impact"]["python-docx"]["reaches"])
    assert "ooxml-core" in reaches


def test_order_graph_reports_a_runtime_cycle(tmp_path):
    root = build_workspace(tmp_path)
    write(
        root / "ooxml-core/pyproject.toml",
        '[project]\nname = "ooxml-core"\nversion = "0.6.0"\n'
        'dependencies = ["python-docx @ git+https://github.com/ooxml-stack/python-docx.git@v1.2.0"]\n',
    )
    plan = build(root)
    assert plan["graphs"]["partial_release_order"]["cycle"]
    assert any(item["code"] == "release_order_cycle" for item in plan["diagnostics"])


# ----------------------------------------------------------------------- full


def test_full_binding_records_the_real_job_and_matrix(tmp_path):
    plan = build(build_workspace(tmp_path))
    job = plan["full"]["ooxml-core"]["jobs"][0]
    assert job["id"] == "full"
    assert job["name"] == "full gate"
    assert job["matrix"] == {"python-version": ["3.12"]}
    assert job["steps"][1]["run"] == "make full\nmake check\n"


def test_full_binding_records_job_and_step_env(tmp_path):
    root = build_workspace(tmp_path)
    write(root / "ooxml-core/.github/workflows/full.yml", WORKFLOW_FULL_ENV)
    plan = build(root)
    job = plan["full"]["ooxml-core"]["jobs"][0]
    assert job["env"] == {"UV_PYTHON": "3.12", "UV_GIT_PREFER_CLI": "true"}
    assert job["steps"][0]["env"] == {"NEEDS_JSON": "${{ toJSON(needs) }}"}


def test_full_binding_records_source_lines(tmp_path):
    """Every binding points back at the workflow line it was read from."""
    job = build(build_workspace(tmp_path))["full"]["ooxml-core"]["jobs"][0]
    assert job["line"] == 4
    assert [step["line"] for step in job["steps"]] == [12, 13, 17]


def test_full_binding_reports_a_missing_job(tmp_path):
    policy = make_policy(
        full_bindings={"ooxml-core": {"workflow": ".github/workflows/full.yml", "jobs": ["ghost"]}}
    )
    plan = build(build_workspace(tmp_path, policy))
    assert any(item["code"] == "command_source_mismatch" for item in plan["diagnostics"])


def test_an_unsupported_workflow_structure_is_a_structural_error(tmp_path):
    """A structure the parser cannot read must be reported, never silently dropped."""
    root = build_workspace(tmp_path)
    write(root / "ooxml-core/.github/workflows/full.yml", WORKFLOW_ENV_NESTED)
    plan = build(root)
    assert any(item["code"] == "unsupported_workflow" for item in plan["diagnostics"])
    assert plan["full"]["ooxml-core"]["jobs"][0]["env"] == {}


def test_full_binding_reports_a_missing_workflow(tmp_path):
    policy = make_policy(
        full_bindings={"ooxml-core": {"workflow": ".github/workflows/absent.yml", "jobs": ["full"]}}
    )
    plan = build(build_workspace(tmp_path, policy))
    assert any(item["code"] == "command_source_mismatch" for item in plan["diagnostics"])


# ----------------------------------------------------------------------- plan


def test_plan_is_byte_identical_across_workspace_roots(tmp_path):
    first = inputs.canonical_json(build(build_workspace(tmp_path / "one")))
    second = inputs.canonical_json(build(build_workspace(tmp_path / "two")))
    assert first == second


def test_plan_excludes_git_and_local_state(tmp_path):
    text = inputs.canonical_json(build(build_workspace(tmp_path)))
    for forbidden in ('"common_dir"', '"scanned_at"', '"worktrees"', '"remote":', '"head":'):
        assert forbidden not in text


def test_plan_records_policy_summary(tmp_path):
    plan = build(build_workspace(tmp_path))
    node = next(item for item in plan["nodes"] if item["key"] == "python-docx")
    assert (node["layer"], node["cadence"], node["visibility"]) == ("app", "per-commit", "public")
    assert node["version"] == "1.2.0"