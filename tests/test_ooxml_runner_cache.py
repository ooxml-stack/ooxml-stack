"""

# pyright: reportMissingImports=falseVersioned cache READY manifests and normal-run preflight."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from runner_fixtures import REPO, make_plan, make_repo

from ooxml_runner import cache, cli, docker


COMPONENTS = ("repositories", "corpus", "dotnet")


def _cache(root: Path) -> Path:
    root.mkdir()
    for name in COMPONENTS:
        (root / name).mkdir()
        (root / name / "marker.txt").write_text(f"{name} v1")
    return root


def test_missing_ready_manifest_fails_closed(tmp_path):
    root = _cache(tmp_path / "cache")
    with pytest.raises(cache.CacheError, match="missing"):
        cache.validate(root, COMPONENTS)


def test_corrupt_manifest_fails_closed(tmp_path):
    root = _cache(tmp_path / "cache")
    (root / cache.READY_NAME).write_text("{interrupted")
    with pytest.raises(cache.CacheError, match="not valid JSON"):
        cache.validate(root, COMPONENTS)


def test_changed_cache_content_is_stale(tmp_path):
    root = _cache(tmp_path / "cache")
    cache.repair(root, COMPONENTS)
    (root / "corpus" / "marker.txt").write_text("corpus v2")
    with pytest.raises(cache.CacheError, match="content changed"):
        cache.validate(root, COMPONENTS)


def test_valid_generation_has_identity_components_and_digests(tmp_path):
    root = _cache(tmp_path / "cache")
    written = cache.repair(root, COMPONENTS)
    validated = cache.validate(root, COMPONENTS)

    assert written == validated
    assert validated["ready"] is True
    assert validated["schema_version"] == cache.CACHE_SCHEMA_VERSION
    assert validated["generation_id"].startswith("sha256:")
    assert [row["path"] for row in validated["components"]] == sorted(COMPONENTS)
    assert all(len(row["sha256"]) == 64 for row in validated["components"])
    assert json.loads((root / cache.READY_NAME).read_text()) == validated


def _run(tmp_path, monkeypatch, cache_root):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo)
    observed = cli.identity_module.identity()
    monkeypatch.setenv("OOXML_PLATFORM_BUCKET", "default")
    monkeypatch.setattr(docker.platform, "system", lambda: "Linux")
    monkeypatch.setattr(cli.identity_module, "identity", lambda: dict(observed))
    monkeypatch.setattr(
        cli.identity_module,
        "require_expected",
        lambda candidate, expected: {**candidate, "commit": expected},
    )
    monkeypatch.setattr(docker, "cpu_limit", lambda: 1)
    monkeypatch.setattr(cli.snapshot_module, "credential", lambda: "fixture-token")
    monkeypatch.setattr(
        docker,
        "execute",
        lambda *args: pytest.fail("Docker transport ran without a valid cache generation"),
    )
    return cli.run_repository(
        root=tmp_path,
        repo=REPO,
        commit="HEAD",
        runner_commit=observed["commit"],
        plan=plan,
        output=tmp_path / "out",
        cache_root=cache_root,
    )


def test_normal_run_refuses_missing_ready_before_transport(tmp_path, monkeypatch):
    root = _cache(tmp_path / "cache")
    with pytest.raises(cache.CacheError, match="missing"):
        _run(tmp_path, monkeypatch, root)
    assert not (tmp_path / "out").exists()


def test_explicit_repair_creates_ready_manifest(tmp_path):
    root = _cache(tmp_path / "cache")
    data = cache.ensure(root, repair_cache=True, components=COMPONENTS)
    assert data["ready"] is True
    assert cache.validate(root, COMPONENTS) == data


def test_cli_repair_is_explicit_and_normal_validation_is_required(tmp_path):
    root = _cache(tmp_path / "cache")
    args = cli._parser().parse_args([
        "run", "--root", str(tmp_path), "--repo", REPO, "--commit", "HEAD",
        "--runner-commit", "a" * 40, "--plan", str(tmp_path / "plan.json"),
        "--output", str(tmp_path / "out"), "--cache-root", str(root),
    ])
    assert args.repair_cache is False
    with pytest.raises(cache.CacheError, match="missing"):
        cache.ensure(root, repair_cache=args.repair_cache, components=COMPONENTS)

    args = cli._parser().parse_args([
        "run", "--root", str(tmp_path), "--repo", REPO, "--commit", "HEAD",
        "--runner-commit", "a" * 40, "--plan", str(tmp_path / "plan.json"),
        "--output", str(tmp_path / "out"), "--cache-root", str(root),
        "--repair-cache",
    ])
    assert args.repair_cache is True
    cache.ensure(root, repair_cache=args.repair_cache, components=COMPONENTS)
    assert cache.validate(root, COMPONENTS)["ready"] is True
