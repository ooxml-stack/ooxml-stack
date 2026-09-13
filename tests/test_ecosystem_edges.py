"""Edge derivation: dependency pins, version policy, snapshot and dedup rules."""

from __future__ import annotations

from ecosystem_fixtures import (
    CORE_SHA,
    CORPUS_SHA,
    DOCX_SHA,
    NODES,
    build,
    build_workspace,
    make_policy,
    write,
)
from ecosystem_workflows import WORKFLOW_TWO_ORGS, WORKFLOW_TWO_ORGS_REVERSED


# ------------------------------------------------------------------- versions


def test_unsupported_constraint_is_reported_not_skipped(tmp_path):
    root = build_workspace(tmp_path)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\nversion = "1.2.0"\n'
        'dependencies = ["ooxml-core^1.0"]\n\n'
        "[tool.uv.sources]\n"
        'ooxml-core = { git = "https://github.com/ooxml-stack/ooxml-core.git", tag = "v0.6.0" }\n',
    )
    plan = build(root)
    assert any(item["code"] == "unsupported_constraint" for item in plan["diagnostics"])


def test_compatible_constraint_violation_is_an_error(tmp_path):
    root = build_workspace(tmp_path)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\nversion = "1.2.0"\n'
        'dependencies = ["ooxml-core~=0.5.0"]\n\n'
        "[tool.uv.sources]\n"
        'ooxml-core = { git = "https://github.com/ooxml-stack/ooxml-core.git", tag = "v0.6.0" }\n',
    )
    plan = build(root)
    assert any(item["code"] == "constraint_violation" for item in plan["diagnostics"])


def test_local_version_violating_a_public_constraint_is_an_error(tmp_path):
    """``1.0+local`` must not satisfy ``!=1.0`` (the local segment is ignored)."""
    root = build_workspace(tmp_path)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\nversion = "1.2.0"\n'
        'dependencies = ["ooxml-core!=1.0"]\n\n'
        "[tool.uv.sources]\n"
        'ooxml-core = { git = "https://github.com/ooxml-stack/ooxml-core.git", tag = "v1.0" }\n',
    )
    write(
        root / "python-docx/uv.lock",
        "[[package]]\n"
        'name = "ooxml-core"\n'
        'version = "1.0+local"\n'
        f'source = {{ git = "https://github.com/ooxml-stack/ooxml-core.git?tag=v1.0#{CORE_SHA}" }}\n',
    )
    plan = build(root)
    assert any(item["code"] == "constraint_violation" for item in plan["diagnostics"])


def test_require_uniform_repos_scope_is_honoured(tmp_path):
    policy = make_policy(
        require_uniform=[{"upstream": "ooxml-core", "role": "runtime", "repos": ["python-pptx"]}]
    )
    plan = build(build_workspace(tmp_path, policy))
    skew = next(item for item in plan["diagnostics"] if item["code"] == "version_skew")
    assert skew["scope"] == "required"
    group = next(g for g in plan["version_groups"] if g["upstream"] == "ooxml-core")
    assert group["required_repos"] == ["python-pptx"]


def test_unscoped_skew_is_still_reported(tmp_path):
    policy = make_policy(require_uniform=[])
    plan = build(build_workspace(tmp_path, policy))
    skew = next(item for item in plan["diagnostics"] if item["code"] == "version_skew")
    assert skew["scope"] == "unscoped"


# ---------------------------------------------------------------------- edges


def test_uv_sources_ref_wins_over_the_direct_spec(tmp_path):
    root = build_workspace(tmp_path)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\nversion = "1.2.0"\n'
        'dependencies = ["ooxml-core @ git+https://github.com/ooxml-stack/ooxml-core.git@v0.6.0"]\n\n'
        "[tool.uv.sources]\n"
        'ooxml-core = { git = "https://github.com/ooxml-stack/ooxml-core.git", tag = "v9.9.9" }\n',
    )
    plan = build(root)
    edge = next(e for e in plan["edges"] if e["to"] == "ooxml-core" and e["from"] == "python-docx")
    assert edge["declared"]["ref_raw"] == "v9.9.9"
    assert any(item["code"] == "source_override_conflict" for item in plan["diagnostics"])


def test_uv_sources_url_conflict_is_reported(tmp_path):
    root = build_workspace(tmp_path)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\nversion = "1.2.0"\n'
        'dependencies = ["ooxml-core @ git+https://github.com/ooxml-stack/ooxml-core.git@v0.6.0"]\n\n'
        "[tool.uv.sources]\n"
        'ooxml-core = { git = "https://github.com/other-org/ooxml-core.git", tag = "v0.6.0" }\n',
    )
    plan = build(root)
    assert any(item["code"] == "source_override_conflict" for item in plan["diagnostics"])


def test_uv_sources_branch_selector_is_preserved(tmp_path):
    """A branch selector must survive into the plan so the scan can honour it."""
    root = build_workspace(tmp_path)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\nversion = "1.2.0"\n'
        'dependencies = ["ooxml-core"]\n\n'
        "[tool.uv.sources]\n"
        'ooxml-core = { git = "https://github.com/ooxml-stack/ooxml-core.git", branch = "stable" }\n',
    )
    plan = build(root)
    edge = next(e for e in plan["edges"] if e["from"] == "python-docx" and e["to"] == "ooxml-core")
    assert edge["declared"]["ref_raw"] == "stable"
    assert edge["declared"]["ref_declared_kind"] == "branch"


def test_lock_url_disagreeing_with_the_declaration_is_reported(tmp_path):
    root = build_workspace(tmp_path)
    write(
        root / "python-docx/uv.lock",
        "[[package]]\n"
        'name = "ooxml-core"\n'
        'version = "0.6.0"\n'
        f'source = {{ git = "https://github.com/other-org/ooxml-core.git?tag=v0.6.0#{CORE_SHA}" }}\n',
    )
    plan = build(root)
    assert any(item["code"] == "source_override_conflict" for item in plan["diagnostics"])


def test_git_dependency_without_a_ref_is_an_error(tmp_path):
    root = build_workspace(tmp_path)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\nversion = "1.2.0"\n'
        'dependencies = ["ooxml-core @ git+https://github.com/ooxml-stack/ooxml-core.git"]\n',
    )
    plan = build(root)
    assert any(item["code"] == "unpinned_dependency" for item in plan["diagnostics"])


def test_git_lock_entry_without_a_full_sha_is_an_error(tmp_path):
    """A git lock entry with no ``#<sha>`` fragment cannot pin anything."""
    root = build_workspace(tmp_path)
    write(
        root / "python-docx/uv.lock",
        "[[package]]\n"
        'name = "ooxml-core"\n'
        'version = "0.6.0"\n'
        'source = { git = "https://github.com/ooxml-stack/ooxml-core.git?tag=v0.6.0" }\n',
    )
    plan = build(root)
    assert any(
        item["code"] == "lock_missing" and "full commit SHA" in item["detail"]
        for item in plan["diagnostics"]
    )


def test_dependency_on_an_unknown_node_is_a_structural_error(tmp_path):
    root = build_workspace(tmp_path)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\nversion = "1.2.0"\n'
        'dependencies = ["ooxml-ghost @ git+https://github.com/ooxml-stack/ooxml-ghost.git@v1.0.0"]\n',
    )
    plan = build(root)
    assert any(item["code"] == "policy_node_mismatch" for item in plan["diagnostics"])


def test_snapshot_edge_to_an_unknown_node_is_an_error(tmp_path):
    root = build_workspace(tmp_path)
    write(
        root / "ooxml-core/ci/environment.json",
        '{"repositories": {"ooxml-ghost": "' + DOCX_SHA + '"}, "corpus": {"release_tag": "x"}}',
    )
    plan = build(root)
    assert any(item["code"] == "policy_node_mismatch" for item in plan["diagnostics"])


def test_corpus_edge_to_an_undeclared_node_is_an_error(tmp_path):
    policy = make_policy(nodes=[n for n in NODES if n["key"] != "ooxml-native-corpus"])
    plan = build(build_workspace(tmp_path, policy))
    assert any(item["code"] == "policy_node_mismatch" for item in plan["diagnostics"])
    assert not [edge for edge in plan["edges"] if edge["kind"] == "data"]


def test_corpus_edge_records_tag_and_commit_separately(tmp_path):
    plan = build(build_workspace(tmp_path))
    data = next(edge for edge in plan["edges"] if edge["kind"] == "data")
    assert data["declared"]["release_tag"] == "native-corpus-2026-08-15.1"
    assert data["declared"]["ref_declared_kind"] == "release_tag"
    assert data["expected"]["commit"] == CORPUS_SHA


# ---------------------------------------------------------------------- dedup


def test_edges_with_different_urls_are_not_deduplicated(tmp_path):
    """Two owners of the same repo name are two claims, each needing its own query."""
    root = build_workspace(tmp_path)
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_TWO_ORGS)
    plan = build(root)
    uses = [e for e in plan["edges"] if e.get("purpose") == "workflow_uses"]
    assert sorted(e["declared"]["url"] for e in uses) == [
        "https://github.com/ooxml-stack/ooxml-stack",
        "https://github.com/other-org/ooxml-stack",
    ]


def test_edge_order_does_not_change_the_edge_set(tmp_path):
    """Reordering the declarations must not change which edges exist, or their order."""

    def shape(root):
        return [
            (
                edge["from"],
                edge["to"],
                edge["kind"],
                edge.get("purpose"),
                edge["declared"].get("url"),
                edge["declared"].get("ref_raw"),
            )
            for edge in build(root)["edges"]
        ]

    first = build_workspace(tmp_path / "one")
    write(first / "python-docx/.github/workflows/ci.yml", WORKFLOW_TWO_ORGS)
    second = build_workspace(tmp_path / "two")
    write(second / "python-docx/.github/workflows/ci.yml", WORKFLOW_TWO_ORGS_REVERSED)
    assert shape(first) == shape(second)


def test_identical_declarations_still_merge_their_sites(tmp_path):
    root = build_workspace(tmp_path)
    write(
        root / "python-docx/.github/workflows/ci.yml",
        "name: ci\non: [push]\njobs:\n  test:\n    steps:\n"
        "      - uses: ooxml-stack/ooxml-stack/.github/workflows/plan.yml@v1.0.0\n"
        "      - uses: ooxml-stack/ooxml-stack/.github/workflows/plan.yml@v1.0.0\n",
    )
    plan = build(root)
    uses = [e for e in plan["edges"] if e.get("purpose") == "workflow_uses"]
    assert len(uses) == 1
    assert len(uses[0]["sites"]) == 2