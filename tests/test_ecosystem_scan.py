"""Scan-side acceptance tests: transient diagnostics and repo identity."""

from __future__ import annotations

from ecosystem_fixtures import (
    CORE_SHA,
    FRAMEWORK_SHA,
    build,
    build_workspace,
    git,
    init_repo,
    seal,
    sealed_workspace,
    write,
)
from ecosystem_workflows import (
    WORKFLOW_DOCX_FLOATING,
    WORKFLOW_DOCX_OTHER_ORG,
    WORKFLOW_DOCX_TAG,
    WORKFLOW_TWO_ORGS,
)
from scripts.ooxml_ci import gitfacts, inputs, scan as scan_mod

EMPTY_LISTING = {"ok": True, "tags": {}, "peeled": {}, "heads": {}}


def _tags(**tags):
    return {"ok": True, "tags": dict(tags), "peeled": {}, "heads": {}}


def test_offline_scan_marks_every_git_ref_unverifiable_and_required(tmp_path):
    root = sealed_workspace(tmp_path)
    policy = inputs.load_policy(root)
    report = scan_mod.scan(root, policy, build(root), offline=True)
    unverifiable = [item for item in report["diagnostics"] if item["code"] == "unverifiable"]
    assert unverifiable
    assert all(item["level"] == "unverifiable" and item["required"] for item in unverifiable)


def test_offline_scan_still_flags_ci_refs_as_required_unverifiable(tmp_path):
    """An offline run must not silently skip workflow ``uses:`` refs."""
    root = sealed_workspace(tmp_path)
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_DOCX_FLOATING)
    policy = inputs.load_policy(root)
    report = scan_mod.scan(root, policy, build(root), offline=True)
    ci = [
        item
        for item in report["diagnostics"]
        if item["code"] == "unverifiable" and "ci.yml" in item["where"]
    ]
    assert ci
    assert all(item["level"] == "unverifiable" and item["required"] for item in ci)


def test_offline_scan_records_ci_refs_as_unverifiable(tmp_path):
    root = sealed_workspace(tmp_path)
    policy = inputs.load_policy(root)
    report = scan_mod.scan(root, policy, build(root), offline=True)
    ci = [item for item in report["refs"] if item["purpose"] == "workflow_uses"]
    assert ci
    assert all(item["resolved"]["kind"] == "unverifiable" for item in ci)


def test_scan_records_ci_refs_like_package_pins(tmp_path, monkeypatch):
    """CI refs share the package-pin recording surface, not just the diagnostics."""
    root = sealed_workspace(tmp_path)
    policy = inputs.load_policy(root)
    monkeypatch.setattr(gitfacts, "remote_refs", lambda *a, **k: _tags(**{"v1.0.0": "9" * 40}))
    report = scan_mod.scan(root, policy, build(root), offline=False)
    ci = [item for item in report["refs"] if item["purpose"] == "workflow_uses"]
    assert ci
    assert ci[0]["ref"] == "v1.0.0"
    assert ci[0]["declared_kind"] == "unknown"  # syntax-level; the scan is authoritative
    assert ci[0]["resolved"] == {"kind": "lightweight_tag", "commit": "9" * 40}
    assert ci[0]["remote"] == "https://github.com/ooxml-stack/ooxml-stack"


def test_scan_queries_the_declared_url_not_the_checkout_origin(tmp_path, monkeypatch):
    """A declaration pointing at another repo must be queried, not the local origin."""
    root = sealed_workspace(tmp_path)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\nversion = "1.2.0"\n'
        'dependencies = ["ooxml-core @ git+https://github.com/other-org/ooxml-core.git@v0.6.0"]\n',
    )
    policy = inputs.load_policy(root)
    seen: list[str] = []

    def fake(remote_url, cwd, timeout, cache):
        seen.append(remote_url)
        return _tags(**{"v0.6.0": CORE_SHA})

    monkeypatch.setattr(gitfacts, "remote_refs", fake)
    report = scan_mod.scan(root, policy, build(root), offline=False)
    assert "https://github.com/other-org/ooxml-core.git" in seen
    assert any(
        item["code"] == "policy_repo_mismatch" and item.get("direction") == "remote_mismatch"
        for item in report["diagnostics"]
    )


def test_scan_queries_the_declared_ci_url(tmp_path, monkeypatch):
    """A ``uses:`` ref must be queried at the URL its owner/repo names."""
    root = sealed_workspace(tmp_path)
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_DOCX_OTHER_ORG)
    policy = inputs.load_policy(root)
    seen: list[str] = []

    def fake(remote_url, cwd, timeout, cache):
        seen.append(remote_url)
        return _tags(**{"v1.0.0": "9" * 40})

    monkeypatch.setattr(gitfacts, "remote_refs", fake)
    report = scan_mod.scan(root, policy, build(root), offline=False)
    assert "https://github.com/other-org/ooxml-stack" in seen
    assert any(
        item["code"] == "policy_repo_mismatch" and item.get("direction") == "remote_mismatch"
        for item in report["diagnostics"]
    )


def test_scan_queries_every_declared_ci_url(tmp_path, monkeypatch):
    """Declaration order must not decide which of two same-named repos gets verified."""
    root = sealed_workspace(tmp_path)
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_TWO_ORGS)
    policy = inputs.load_policy(root)
    seen: list[str] = []

    def fake(remote_url, cwd, timeout, cache):
        seen.append(remote_url)
        if "other-org" in remote_url:
            return EMPTY_LISTING
        return _tags(**{"v1.0.0": "9" * 40})

    monkeypatch.setattr(gitfacts, "remote_refs", fake)
    report = scan_mod.scan(root, policy, build(root), offline=False)
    assert "https://github.com/ooxml-stack/ooxml-stack" in seen
    assert "https://github.com/other-org/ooxml-stack" in seen
    assert any(
        item["code"] == "missing_ref" and "other-org" in item["detail"]
        for item in report["diagnostics"]
    )


def test_scan_honours_a_declared_branch_selector(tmp_path, monkeypatch):
    """A branch declaration must not be masked by a same-named tag."""
    root = build_workspace(tmp_path)
    heads = seal(root)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\nversion = "1.2.0"\n'
        'dependencies = ["ooxml-core"]\n\n'
        "[tool.uv.sources]\n"
        'ooxml-core = { git = "https://github.com/ooxml-stack/ooxml-core.git", branch = "stable" }\n',
    )
    policy = inputs.load_policy(root)
    monkeypatch.setattr(
        gitfacts,
        "remote_refs",
        lambda *a, **k: {
            "ok": True,
            "tags": {"stable": heads["ooxml-core"]},
            "peeled": {},
            "heads": {"stable": "9" * 40},
        },
    )
    report = scan_mod.scan(root, policy, build(root), offline=False)
    assert any(item["code"] == "unreproducible_ref" for item in report["diagnostics"])


def test_scan_records_the_corpus_release_tag(tmp_path, monkeypatch):
    """The data tag is measured for resolvability, never compared to the repo SHA."""
    root = sealed_workspace(tmp_path)
    policy = inputs.load_policy(root)
    monkeypatch.setattr(
        gitfacts, "remote_refs", lambda *a, **k: _tags(**{"native-corpus-2026-08-15.1": "7" * 40})
    )
    report = scan_mod.scan(root, policy, build(root), offline=False)
    entry = next(item for item in report["refs"] if item["kind"] == "data")
    assert entry["ref"] == "native-corpus-2026-08-15.1"
    assert entry["declared_kind"] == "release_tag"
    assert entry["resolved"] == {"kind": "lightweight_tag", "commit": "7" * 40}
    assert not any(
        item["code"] == "lock_commit_mismatch" and "ooxml-native-corpus" in item["where"]
        for item in report["diagnostics"]
    )


def test_scan_reports_the_corpus_release_tag_as_missing(tmp_path, monkeypatch):
    root = sealed_workspace(tmp_path)
    policy = inputs.load_policy(root)
    monkeypatch.setattr(gitfacts, "remote_refs", lambda *a, **k: EMPTY_LISTING)
    report = scan_mod.scan(root, policy, build(root), offline=False)
    assert any(
        item["code"] == "missing_ref" and "native-corpus-2026-08-15.1" in item["detail"]
        for item in report["diagnostics"]
    )


def test_scan_reports_a_missing_remote_ref(tmp_path, monkeypatch):
    root = sealed_workspace(tmp_path)
    policy = inputs.load_policy(root)
    monkeypatch.setattr(gitfacts, "remote_refs", lambda *a, **k: EMPTY_LISTING)
    report = scan_mod.scan(root, policy, build(root), offline=False)
    missing = [item for item in report["diagnostics"] if item["code"] == "missing_ref"]
    assert missing and all(item["level"] == "error" for item in missing)


def test_scan_reports_a_lock_commit_mismatch(tmp_path, monkeypatch):
    root = sealed_workspace(tmp_path)
    policy = inputs.load_policy(root)
    monkeypatch.setattr(
        gitfacts,
        "remote_refs",
        lambda *a, **k: _tags(**{"v0.6.0": "9" * 40, "v0.6.1": CORE_SHA, "v0.5.37": FRAMEWORK_SHA}),
    )
    report = scan_mod.scan(root, policy, build(root), offline=False)
    mismatch = [item for item in report["diagnostics"] if item["code"] == "lock_commit_mismatch"]
    assert mismatch and mismatch[0]["level"] == "error"


def test_scan_flags_a_branch_ci_ref(tmp_path, monkeypatch):
    root = sealed_workspace(tmp_path)
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_DOCX_FLOATING)
    policy = inputs.load_policy(root)
    monkeypatch.setattr(
        gitfacts,
        "remote_refs",
        lambda *a, **k: {"ok": True, "tags": {}, "peeled": {}, "heads": {"main": "9" * 40}},
    )
    report = scan_mod.scan(root, policy, build(root), offline=False)
    assert any(item["code"] == "floating_ci_ref" for item in report["diagnostics"])


def test_scan_accepts_a_tagged_ci_ref(tmp_path, monkeypatch):
    root = sealed_workspace(tmp_path)
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_DOCX_TAG)
    policy = inputs.load_policy(root)
    monkeypatch.setattr(gitfacts, "remote_refs", lambda *a, **k: _tags(**{"v1.0.0": "9" * 40}))
    report = scan_mod.scan(root, policy, build(root), offline=False)
    assert not any(item["code"] == "floating_ci_ref" for item in report["diagnostics"])


def test_scan_ignores_worktrees_of_declared_nodes(tmp_path):
    root = sealed_workspace(tmp_path)
    git(["worktree", "add", "-q", str(root / "python-docx-scratch"), "-b", "scratch"], root / "python-docx")
    policy = inputs.load_policy(root)
    report = scan_mod.scan(root, policy, build(root), offline=True)
    undeclared = [
        item
        for item in report["diagnostics"]
        if item["code"] == "policy_repo_mismatch" and item["direction"] == "undeclared_local"
    ]
    assert undeclared == []


def test_scan_flags_a_genuinely_undeclared_checkout(tmp_path):
    root = sealed_workspace(tmp_path)
    init_repo(root / "ooxml-rogue")
    policy = inputs.load_policy(root)
    report = scan_mod.scan(root, policy, build(root), offline=True)
    undeclared = [
        item
        for item in report["diagnostics"]
        if item["code"] == "policy_repo_mismatch" and item["direction"] == "undeclared_local"
    ]
    assert [item["where"] for item in undeclared] == ["ooxml-rogue"]