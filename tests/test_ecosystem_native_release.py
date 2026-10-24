"""Contract tests for the native release control plane."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest  # pyright: ignore[reportMissingImports]
from cryptography.hazmat.primitives.asymmetric import ed25519  # pyright: ignore[reportMissingImports]

from scripts.native_release import builder
from scripts.native_release.candidate import (
    CandidateError,
    resolve_candidate,
    write_latest_dev,
)
from scripts.native_release.config import ConfigError, load_config
from scripts.native_release.functional import _passed
from scripts.native_release.license_gate import (
    LicenseGateError,
    validate_internal_license,
    validate_release_license,
)
from scripts.native_release.manifest import (
    ManifestError,
    build_manifest,
    validate_manifest,
)
from scripts.native_release.publish import run_transaction
from scripts.native_release.runner import main as native_main
from scripts.native_release.scan import scan_directory

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "release/native-macos-arm64.yaml"


def config():
    return load_config(CONFIG)


def artifacts(digest="a" * 64):
    return {
        "dmg": {
            "sha256": digest,
            "size": 10,
            "notarization": {"status": "notarized", "request_id": "d"},
        },
        "zip": {
            "sha256": "b" * 64,
            "size": 11,
            "notarization": {"status": "notarized", "request_id": "z"},
        },
    }


def test_config_encodes_release_blockers():
    loaded = config()
    assert loaded["runtime"]["fully_native"] is False
    assert loaded["artifacts"]["dmg"]["page_visible"] is True
    assert loaded["artifacts"]["zip"]["page_visible"] is False
    assert loaded["notarization"]["dmg"]["staple"] is True
    assert loaded["notarization"]["zip"]["staple"] is False
    assert "online-staging-acceptance" in loaded["entitlement"]["forbidden_license_ids"]


def test_manifest_contains_both_artifacts_and_immutable_page_url():
    loaded = config()
    manifest = build_manifest(loaded, artifacts(), "TEAMID1234")
    assert set(manifest["artifacts"]) == {"dmg", "zip"}
    assert "/latest/" not in manifest["artifacts"]["dmg"]["url"]
    assert manifest["artifacts"]["dmg"]["package_mode"] == "installer-container"
    assert manifest["artifacts"]["zip"]["package_mode"] == "standalone-directory"
    assert manifest["artifacts"]["dmg"]["checksum_url"].endswith(
        "OOXML-macos-arm64.dmg.sha256"
    )
    assert manifest["artifacts"]["zip"]["checksum_url"].endswith(
        "OOXML-macos-arm64.zip.sha256"
    )
    assert manifest["artifacts"]["zip"]["notarization"]["request_id"] == "z"
    assert manifest["signing_team_id"] == "TEAMID1234"
    broken = json.loads(json.dumps(manifest))
    broken["artifacts"]["dmg"]["url"] = "https://example.test/latest/OOXML.dmg"
    with pytest.raises(ManifestError):
        validate_manifest(broken, loaded)


def test_publish_transaction_updates_latest_last():
    loaded = config()
    manifest = build_manifest(loaded, artifacts(), "TEAMID1234")
    seen = []
    callbacks = {
        step: (lambda step=step: seen.append(step))
        for step in loaded["publish"]["transaction"]
    }
    result = run_transaction(loaded, manifest, callbacks)
    assert seen[-2:] == ["latest:update", "verify:latest"]
    assert result.steps == loaded["publish"]["transaction"]


def test_publish_transaction_refuses_early_latest():
    loaded = config()
    manifest = build_manifest(loaded, artifacts(), "TEAMID1234")
    loaded["publish"]["transaction"] = ["latest:update", "verify:latest"]
    with pytest.raises(ConfigError):
        run_transaction(loaded, manifest, {})


def test_license_gate_rejects_staging_and_accepts_signed_release_test(tmp_path):
    loaded = config()
    private = ed25519.Ed25519PrivateKey.generate()
    loaded["entitlement"]["activation_public_key_hex"] = (
        private.public_key().public_bytes_raw().hex()
    )
    payload = {
        "schema_version": 1,
        "license_id": "release-test-20261020",
        "license_type": "release-test",
        "licensee": "External Release QA",
        "product_id": "ooxml-operation-engine",
        "artifact_id": loaded["runtime"]["artifact_id"],
        "not_before": "2026-01-01",
        "expiry": "2026-12-31",
    }
    payload["signature"] = private.sign(canonical(payload)).hex()
    path = tmp_path / "release-test.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    summary = validate_release_license(path, loaded, today=date(2026, 10, 20))
    assert summary["license_type"] == "release-test"
    assert "signature" not in summary
    payload["license_id"] = "online-staging-acceptance"
    payload["signature"] = private.sign(canonical(payload)).hex()
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LicenseGateError):
        validate_release_license(path, loaded, today=date(2026, 10, 20))
    internal = validate_internal_license(path, loaded, today=date(2026, 10, 20))
    assert internal["mode"] == "DEV_ONLY"


def test_functional_pass_requires_all_surfaces():
    loaded = config()
    steps = {
        "version": {"exit_code": 0},
        "unlicensed_status": {
            "json": {"serving": "inactive", "reason": "license_missing"}
        },
        "activate": {"exit_code": 0},
        "status": {"json": {"serving": "active"}},
        "word": {
            "apply": {"json": {"success": True}},
            "validate": {"json": {"passed": True}},
        },
        "excel": {
            "apply": {"json": {"success": True}},
            "validate": {"json": {"passed": True}},
        },
        "pptx": {"expected_refusal": True},
        "pdf": {
            "json": {
                "available": False,
                "error": {"code": "pdf_readability_unavailable"},
            }
        },
        "skill": {"exit_code": 0, "installed": True},
        "mcp_core": {"json": {"tool_count": 8}},
        "mcp_workflow": {"json": {"tool_count": 10}},
        "offline_status": {"json": {"serving": "active"}},
        "offline_mcp_core": {"json": {"tool_count": 8}},
        "uninstalled": {"install_absent": True, "license_absent": True},
        "restore_activate": {"exit_code": 0},
        "restore_status": {"json": {"serving": "active"}},
    }
    assert _passed(steps, loaded) is True
    steps["mcp_workflow"]["json"]["tool_count"] = 9
    assert _passed(steps, loaded) is False


def test_release_fails_closed_without_developer_id(monkeypatch, capsys):
    for name in (
        "OOXML_NATIVE_DEVELOPER_ID_APPLICATION",
        "OOXML_NATIVE_NOTARY_PROFILE",
        "OOXML_NATIVE_E2E_LICENSE",
    ):
        monkeypatch.delenv(name, raising=False)
    code = native_main(["release", "--config", str(CONFIG)])
    captured = capsys.readouterr()
    assert code == 1
    assert "Developer ID Application identity" in captured.err


def test_builder_assembles_stage_from_dist_outputs(tmp_path, monkeypatch):
    loaded = config()
    stage = tmp_path / "dev/stage"
    client = tmp_path / "client.dist"
    engine = tmp_path / "engine.dist"
    client.mkdir()
    engine.mkdir()
    (client / "ooxml").write_text("client", encoding="utf-8")
    (engine / "ooxml-engine").write_text("engine", encoding="utf-8")
    monkeypatch.setattr(builder, "_wheelhouse", lambda *_args: tmp_path)
    monkeypatch.setattr(builder, "_build_env", lambda *_args: (tmp_path / "env", False))
    monkeypatch.setattr(builder, "_build_client", lambda *_args: client)
    monkeypatch.setattr(builder, "_build_engine", lambda *_args: engine)
    monkeypatch.setattr(builder, "_copy_public_metadata", lambda *_args: None)
    result = builder.build_stage(loaded, stage, "dev", env={})
    assert result == stage
    assert (stage / "bin/ooxml").is_symlink()
    assert (stage / "lib/ooxml-engine/ooxml-engine").is_file()


def test_release_builder_refuses_reused_environment(tmp_path):
    loaded = config()
    build_env = tmp_path / "env"
    (build_env / "bin").mkdir(parents=True)
    (build_env / "bin/python").write_text("", encoding="utf-8")
    with pytest.raises(builder.BuildError):
        builder._build_env(
            loaded,
            tmp_path,
            {loaded["build"]["build_env_env"]: str(build_env)},
            "release",
        )


def test_candidate_requires_explicit_selection(tmp_path):
    with pytest.raises(CandidateError):
        resolve_candidate(None, tmp_path, allow_latest_dev=True)
    candidate = tmp_path / "OOXML.dmg"
    candidate.write_bytes(b"x")
    write_latest_dev(tmp_path, candidate)
    assert (
        resolve_candidate("latest-dev", tmp_path, allow_latest_dev=True)
        == candidate.resolve()
    )
    with pytest.raises(CandidateError):
        resolve_candidate("latest-dev", tmp_path, allow_latest_dev=False)


def test_scan_distinguishes_parser_string_from_secret(tmp_path):
    loaded = config()
    (tmp_path / "parser.txt").write_text(
        "BEGIN OPENSSH PRIVATE KEY\n", encoding="utf-8"
    )
    result = scan_directory(tmp_path, loaded)
    assert result["pass"] is True
    assert result["allowed_strings"]
    (tmp_path / "bad.py").write_text("source", encoding="utf-8")
    result = scan_directory(tmp_path, loaded)
    assert result["pass"] is False
    assert any(name.endswith("bad.py") for name in result["forbidden_entries"])


def test_scan_rejects_real_private_key_block(tmp_path):
    loaded = config()
    body = "A" * 128
    pem = f"-----BEGIN OPENSSH PRIVATE KEY-----\n{body}\n-----END OPENSSH PRIVATE KEY-----\n"
    (tmp_path / "key.txt").write_text(pem, encoding="utf-8")
    result = scan_directory(tmp_path, loaded)
    assert result["pass"] is False
    assert result["secrets"][0]["kind"] == "private-key-block"


def canonical(payload):
    unsigned = {key: value for key, value in payload.items() if key != "signature"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")


def test_build_wheelhouse_requires_destination(monkeypatch, capsys):
    for name in (
        "OOXML_NATIVE_DEVELOPER_ID_APPLICATION",
        "OOXML_NATIVE_NOTARY_PROFILE",
        "OOXML_NATIVE_E2E_LICENSE",
    ):
        monkeypatch.delenv(name, raising=False)
    code = native_main(["build-wheelhouse", "--config", str(CONFIG)])
    captured = capsys.readouterr()
    assert code == 1
    assert "--wheelhouse is required" in captured.err


def test_wheelhouse_rejects_dirty_source(tmp_path, monkeypatch):
    from scripts.native_release import wheelhouse

    loaded = config()
    loaded["_repo_root"] = str(tmp_path)
    for name in loaded["sources"]:
        repo = tmp_path / loaded["sources"][name]
        repo.mkdir(parents=True)
        monkeypatch.setattr(
            wheelhouse,
            "_git",
            lambda repo, *args: "HEAD" if args == ("rev-parse", "HEAD") else " M dirty",
        )
    with pytest.raises(wheelhouse.WheelhouseError, match="dirty"):
        wheelhouse.build_wheelhouse(
            loaded, tmp_path / "wheelhouse", tmp_path / "lock.json", env={}
        )


def test_release_local_skips_publish(monkeypatch, tmp_path):
    from scripts.native_release import release

    sentinel = {"status": "ready"}
    calls = {"publish": 0, "notarize": 0}

    monkeypatch.setattr(
        release,
        "release_credentials",
        lambda _config: type("C", (), {"identity": "Developer ID Application: Test"})(),
    )
    monkeypatch.setattr(release, "_required_env", lambda _name: "/tmp/license.json")
    monkeypatch.setattr(release, "validate_release_license", lambda *_args: {})
    monkeypatch.setattr(release, "_require_clean_sources", lambda _config: None)
    monkeypatch.setattr(release, "_wheelhouse", lambda _config: tmp_path)
    monkeypatch.setattr(release, "verify_inputs", lambda *_args: {})
    monkeypatch.setattr(release, "release_target", lambda _config: "a" * 40)
    monkeypatch.setattr(
        release,
        "EvidenceSeal",
        lambda _path: type(
            "E",
            (),
            {
                "root": tmp_path,
                "write": lambda self, *_args: None,
                "finalize_prepublish": lambda self, payload: {"seal": payload["mode"]},
            },
        )(),
    )
    monkeypatch.setattr(release, "_stage", lambda *_args: tmp_path / "stage")
    monkeypatch.setattr(release, "build_stage", lambda *_args: None)
    monkeypatch.setattr(release, "_require_stage", lambda _path: None)
    monkeypatch.setattr(release, "strip_payload", lambda _path: None)
    monkeypatch.setattr(
        release, "normalized_payload_sha256", lambda *_args, **_kwargs: "hash"
    )
    monkeypatch.setattr(release, "sign_payload", lambda *_args: [])
    monkeypatch.setattr(
        release, "verify_payload_signatures", lambda *_args, **_kwargs: "TEAM"
    )
    monkeypatch.setattr(release, "create_artifacts", lambda *_args: {})
    monkeypatch.setattr(release, "_finish_release", lambda *args: sentinel)

    result = release.run_release(config(), None, publish=False)
    assert result is sentinel
