"""Negative contracts for native release publication."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest  # pyright: ignore[reportMissingImports]

from scripts.native_release import live_verify
from scripts.native_release import publish as publish_control
from scripts.native_release import publish_github_release as publisher
from scripts.native_release.config import ConfigError, load_config
from scripts.native_release.publish import release_target

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "release/native-macos-arm64.yaml"


def _manifest():
    dmg = b"dmg-payload"
    zip_payload = b"zip-payload"
    base = (
        "https://github.com/ooxml-stack/ooxml-stack/releases/download/"
        "native-v1-abcdef123456"
    )
    latest = (
        "https://github.com/ooxml-stack/ooxml-stack/releases/latest/download/"
        "manifest.json"
    )
    manifest = {
        "client_version": "1.0.0",
        "latest": {"manifest_url": latest},
        "artifacts": {
            "dmg": {
                "url": f"{base}/OOXML-macos-arm64.dmg",
                "checksum_url": f"{base}/OOXML-macos-arm64.dmg.sha256",
                "filename": "OOXML-macos-arm64.dmg",
                "sha256": hashlib.sha256(dmg).hexdigest(),
                "size": len(dmg),
            },
            "zip": {
                "url": f"{base}/OOXML-macos-arm64.zip",
                "checksum_url": f"{base}/OOXML-macos-arm64.zip.sha256",
                "filename": "OOXML-macos-arm64.zip",
                "sha256": hashlib.sha256(zip_payload).hexdigest(),
                "size": len(zip_payload),
            },
        },
    }
    versioned_url = f"{base}/manifest.json"
    payloads = {
        manifest["artifacts"]["dmg"]["url"]: dmg,
        manifest["artifacts"]["dmg"]["checksum_url"]: live_verify.checksum_payload(
            manifest["artifacts"]["dmg"]
        ),
        manifest["artifacts"]["zip"]["url"]: zip_payload,
        manifest["artifacts"]["zip"]["checksum_url"]: live_verify.checksum_payload(
            manifest["artifacts"]["zip"]
        ),
        versioned_url: json.dumps(manifest).encode("utf-8"),
        latest: json.dumps(manifest).encode("utf-8"),
    }
    return manifest, payloads


def test_release_target_requires_explicit_commit(monkeypatch):
    config = load_config(CONFIG)
    monkeypatch.delenv("OOXML_NATIVE_RELEASE_COMMIT", raising=False)
    with pytest.raises(ConfigError, match="OOXML_NATIVE_RELEASE_COMMIT"):
        release_target(config)


def test_release_target_must_be_reachable_from_remote_branch(monkeypatch):
    target = "a" * 40

    def fake_run(command):
        if "for-each-ref" in command:
            return SimpleNamespace(stdout="")
        return SimpleNamespace(stdout=f"{target}\n")

    monkeypatch.setattr(publish_control, "_run_command", fake_run)
    with pytest.raises(ConfigError, match="not reachable from a remote branch"):
        publish_control.assert_remote_branch_contains(target)


def test_release_creation_pins_target(monkeypatch):
    target = "b" * 40
    commands = []
    monkeypatch.setattr(
        publisher.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )
    monkeypatch.setattr(publisher, "_run", lambda command: commands.append(command))
    publisher._ensure_release("native-v1-test", target)
    create = next(command for command in commands if "create" in command)
    assert create[create.index("--target") + 1] == target


def test_existing_asset_same_size_different_digest_fails(tmp_path, monkeypatch):
    path = tmp_path / "asset.bin"
    path.write_bytes(b"local")
    monkeypatch.setattr(
        publisher,
        "_asset_map",
        lambda _tag: {
            path.name: {
                "size": path.stat().st_size,
                "digest": f"sha256:{'f' * 64}",
            }
        },
    )
    with pytest.raises(ValueError, match="different content"):
        publisher._upload("native-v1-test", path, path.name)


def test_existing_asset_without_digest_is_downloaded_and_hashed(tmp_path, monkeypatch):
    path = tmp_path / "asset.bin"
    path.write_bytes(b"local")
    monkeypatch.setattr(
        publisher,
        "_asset_map",
        lambda _tag: {
            path.name: {
                "size": path.stat().st_size,
                "url": "https://example.test/asset.bin",
            }
        },
    )
    monkeypatch.setattr(live_verify, "fetch_url", lambda _url: (200, b"other"))
    with pytest.raises(ValueError, match="different content"):
        publisher._upload("native-v1-test", path, path.name)


def test_checksum_content_mismatch_fails(monkeypatch):
    manifest, payloads = _manifest()
    payloads[manifest["artifacts"]["dmg"]["checksum_url"]] = b"wrong checksum\n"
    monkeypatch.setattr(live_verify, "fetch_url", lambda url: (200, payloads[url]))
    with pytest.raises(ValueError, match="HTTP content mismatch"):
        publisher._verify_assets("native-v1-test", manifest)


def test_versioned_manifest_mismatch_fails(monkeypatch):
    manifest, payloads = _manifest()
    changed = json.loads(json.dumps(manifest))
    changed["client_version"] = "9.9.9"
    versioned_url = (
        manifest["artifacts"]["dmg"]["url"].rsplit("/", 1)[0] + "/manifest.json"
    )
    payloads[versioned_url] = json.dumps(changed).encode("utf-8")
    monkeypatch.setattr(live_verify, "fetch_url", lambda url: (200, payloads[url]))
    with pytest.raises(ValueError, match="HTTP JSON mismatch"):
        publisher._verify_assets("native-v1-test", manifest)


def test_latest_manifest_mismatch_fails(monkeypatch):
    manifest, payloads = _manifest()
    changed = json.loads(json.dumps(manifest))
    changed["artifact_id"] = "wrong"
    payloads[manifest["latest"]["manifest_url"]] = json.dumps(changed).encode("utf-8")
    monkeypatch.setattr(
        publisher,
        "_run",
        lambda _command: SimpleNamespace(stdout='{"isLatest": true}'),
    )
    monkeypatch.setattr(live_verify, "fetch_url", lambda url: (200, payloads[url]))
    with pytest.raises(ValueError, match="HTTP JSON mismatch"):
        publisher._verify_latest("native-v1-test", manifest)


def test_static_page_without_manifest_contract_is_explicit_blocker():
    manifest, _payloads = _manifest()
    with pytest.raises(
        live_verify.LiveVerifyError,
        match="page blocker: product page does not declare",
    ):
        live_verify.verify_page_contract(
            "<html><body>release notes</body></html>", manifest
        )
