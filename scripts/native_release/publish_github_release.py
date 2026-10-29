"""Execute one native-release transaction step with GitHub Releases."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from . import live_verify
from .publish import assert_remote_branch_contains

REPO = os.environ.get("OOXML_NATIVE_GITHUB_REPO", "ooxml-stack/ooxml-stack")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def main() -> int:
    step = _required("NATIVE_PUBLISH_STEP")
    manifest_path = Path(_required("NATIVE_MANIFEST"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tag = _tag(manifest)
    target = _release_target()
    assert_remote_branch_contains(target)
    if step in {"artifact:dmg", "artifact:zip"}:
        _upload_artifact(
            tag,
            Path(_required("NATIVE_DMG" if step.endswith("dmg") else "NATIVE_ZIP")),
            target,
        )
    elif step in {"checksum:dmg", "checksum:zip"}:
        _upload_checksum(tag, manifest, step.split(":", 1)[1])
    elif step == "manifest:versioned":
        _upload(tag, manifest_path, "manifest.json")
        _run(
            [
                "gh",
                "release",
                "edit",
                tag,
                "--repo",
                REPO,
                "--draft=false",
                "--title",
                tag,
                "--notes",
                f"OOXML native release {tag}",
            ]
        )
    elif step == "page:update":
        _page_update(tag, manifest)
    elif step == "verify:versioned":
        _verify_assets(tag, manifest)
    elif step == "latest:update":
        _run(["gh", "release", "edit", tag, "--repo", REPO, "--latest"])
    elif step == "verify:latest":
        _verify_latest(tag, manifest)
    else:
        raise ValueError(f"unsupported publish step: {step}")
    print(json.dumps({"step": step, "tag": tag, "status": "ok"}))
    return 0


def _release_target() -> str:
    target = (
        (
            os.environ.get("NATIVE_RELEASE_COMMIT")
            or os.environ.get("OOXML_NATIVE_RELEASE_COMMIT")
            or ""
        )
        .strip()
        .lower()
    )
    if not COMMIT_SHA.fullmatch(target):
        raise ValueError("NATIVE_RELEASE_COMMIT must be a full 40-character SHA")
    return target


def _upload_artifact(tag: str, path: Path, target: str) -> None:
    _ensure_release(tag, target)
    _upload(tag, path, path.name)


def _upload_checksum(tag: str, manifest: dict, kind: str) -> None:
    row = manifest["artifacts"][kind]
    source = Path(_required("NATIVE_DMG" if kind == "dmg" else "NATIVE_ZIP"))
    actual = live_verify.sha256_file(source)
    if actual != row["sha256"] or source.stat().st_size != row["size"]:
        raise ValueError(f"local artifact does not match manifest: {source.name}")
    path = source.with_suffix(source.suffix + ".sha256")
    path.write_bytes(live_verify.checksum_payload(row))
    _upload(tag, path, path.name)


def _page_update(tag: str, manifest: dict) -> None:
    metadata = {
        "schema_version": 1,
        "tag": tag,
        "client_version": manifest["client_version"],
        "page_contract": {
            "mode": "manifest-v1",
            "manifest_url": manifest["latest"]["manifest_url"],
        },
        "manifest_url": _versioned_manifest_url(manifest),
        "dmg": manifest["artifacts"]["dmg"],
        "zip": manifest["artifacts"]["zip"],
    }
    path = (
        Path(os.environ.get("NATIVE_EVIDENCE_DIR", tempfile.gettempdir()))
        / "page-metadata.json"
    )
    path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _upload(tag, path, "page-metadata.json")
    live_verify.verify_page_contract_url(_required("NATIVE_PRODUCT_PAGE_URL"), manifest)


def _verify_assets(tag: str, manifest: dict) -> None:
    evidence = []
    for kind, row in manifest["artifacts"].items():
        evidence.append(
            live_verify.verify_artifact_url(
                row["url"],
                row["sha256"],
                row["size"],
                kind=f"{kind}-versioned",
            )
        )
        evidence.append(
            live_verify.verify_content_url(
                row["checksum_url"],
                live_verify.checksum_payload(row),
                kind=f"{kind}-checksum",
            )
        )
    evidence.append(
        live_verify.verify_json_url(
            _versioned_manifest_url(manifest),
            manifest,
            kind="versioned-manifest",
        )
    )
    _write_download_evidence(
        {"tag": tag, "assets": evidence}, "http-download-evidence.json"
    )


def _verify_latest(tag: str, manifest: dict) -> None:
    latest = json.loads(_run(["gh", "api", f"repos/{REPO}/releases/latest"]).stdout)
    if latest.get("tag_name") != tag:
        raise ValueError("tag is not the latest GitHub release")
    latest_manifest_url = manifest["latest"]["manifest_url"]
    if not latest_manifest_url.endswith("/releases/latest/download/manifest.json"):
        raise ValueError("latest manifest URL is not the GitHub latest download URL")
    evidence = [
        live_verify.verify_json_url(
            latest_manifest_url,
            manifest,
            kind="latest-manifest",
        ),
        live_verify.verify_page_manifest_api(
            _required("NATIVE_PAGE_MANIFEST_API_URL"), manifest
        ),
    ]
    latest_root = latest_manifest_url.rsplit("/", 1)[0]
    for kind, row in manifest["artifacts"].items():
        evidence.append(
            live_verify.verify_artifact_url(
                f"{latest_root}/{row['filename']}",
                row["sha256"],
                row["size"],
                kind=f"{kind}-latest",
            )
        )
        evidence.append(
            live_verify.verify_content_url(
                f"{latest_root}/{row['filename']}.sha256",
                live_verify.checksum_payload(row),
                kind=f"{kind}-latest-checksum",
            )
        )
    _write_download_evidence(
        {"tag": tag, "assets": evidence}, "http-latest-evidence.json"
    )


def _ensure_release(tag: str, target: str) -> None:
    exists = subprocess.run(
        ["gh", "release", "view", tag, "--repo", REPO],
        capture_output=True,
        text=True,
        check=False,
    )
    if exists.returncode == 0:
        return
    _run(
        [
            "gh",
            "release",
            "create",
            tag,
            "--repo",
            REPO,
            "--target",
            target,
            "--draft",
            "--title",
            tag,
            "--notes",
            f"Pending native release {tag}",
        ]
    )


def _upload(tag: str, path: Path, name: str) -> None:
    assets = _asset_map(tag)
    size = path.stat().st_size
    digest = live_verify.sha256_file(path)
    if name in assets:
        asset = assets[name]
        if asset.get("size") != size:
            raise ValueError(
                f"release asset already exists with different size: {name}"
            )
        remote_digest = _remote_asset_digest(asset)
        if remote_digest != digest:
            raise ValueError(
                f"release asset already exists with different content: {name}"
            )
        return
    _run(["gh", "release", "upload", tag, str(path), "--repo", REPO])


def _remote_asset_digest(asset: dict[str, Any]) -> str:
    digest = str(asset.get("digest") or "")
    if digest.startswith("sha256:"):
        digest = digest.split(":", 1)[1].lower()
    if SHA256.fullmatch(digest):
        return digest
    url = str(asset.get("url") or "")
    if not url:
        raise ValueError(f"cannot download existing release asset for digest: {asset}")
    _, payload = live_verify.fetch_url(url)
    return live_verify.sha256_bytes(payload)


def _asset_map(tag: str) -> dict:
    raw = _run(["gh", "release", "view", tag, "--repo", REPO, "--json", "assets"])
    return {row["name"]: row for row in json.loads(raw.stdout).get("assets", [])}


def _write_download_evidence(payload: dict, filename: str) -> None:
    root = os.environ.get("NATIVE_EVIDENCE_DIR")
    if root:
        path = Path(root) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _tag(manifest: dict) -> str:
    if os.environ.get("OOXML_NATIVE_RELEASE_TAG"):
        return os.environ["OOXML_NATIVE_RELEASE_TAG"]
    match = re.search(
        r"/releases/download/([^/]+)/", manifest["artifacts"]["dmg"]["url"]
    )
    if not match:
        raise ValueError("cannot derive GitHub release tag from manifest")
    return match.group(1)


def _versioned_manifest_url(manifest: dict) -> str:
    return manifest["artifacts"]["dmg"]["url"].rsplit("/", 1)[0] + "/manifest.json"


def _required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _run(command: list[str]):
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ValueError(
            f"{' '.join(command)} failed: {(result.stderr or result.stdout).strip()}"
        )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
