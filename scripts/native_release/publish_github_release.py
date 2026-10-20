"""Execute one native-release transaction step with GitHub Releases."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

REPO = os.environ.get("OOXML_NATIVE_GITHUB_REPO", "ooxml-stack/ooxml-stack")


def main() -> int:
    step = _required("NATIVE_PUBLISH_STEP")
    manifest_path = Path(_required("NATIVE_MANIFEST"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tag = _tag(manifest)
    if step in {"artifact:dmg", "artifact:zip"}:
        _upload_artifact(
            tag, Path(_required("NATIVE_DMG" if step.endswith("dmg") else "NATIVE_ZIP"))
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
        _verify_latest(tag)
    else:
        raise ValueError(f"unsupported publish step: {step}")
    print(json.dumps({"step": step, "tag": tag, "status": "ok"}))
    return 0


def _upload_artifact(tag: str, path: Path) -> None:
    _ensure_release(tag)
    _upload(tag, path, path.name)


def _upload_checksum(tag: str, manifest: dict, kind: str) -> None:
    row = manifest["artifacts"][kind]
    source = Path(_required("NATIVE_DMG" if kind == "dmg" else "NATIVE_ZIP"))
    checksum = f"{row['sha256']}  {source.name}\n"
    path = source.with_suffix(source.suffix + ".sha256")
    path.write_text(checksum, encoding="utf-8")
    _upload(tag, path, path.name)


def _page_update(tag: str, manifest: dict) -> None:
    metadata = {
        "schema_version": 1,
        "tag": tag,
        "client_version": manifest["client_version"],
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


def _verify_assets(tag: str, manifest: dict) -> None:
    assets = _asset_map(tag)
    for kind, row in manifest["artifacts"].items():
        _verify_http_asset(assets[row["filename"]], row["sha256"], row["size"])
        _verify_http_asset(assets[f"{row['filename']}.sha256"], "", 0)
    manifest_url = _versioned_manifest_url(manifest)
    _verify_http(manifest_url, "", 0)


def _verify_latest(tag: str) -> None:
    view = json.loads(
        _run(
            ["gh", "release", "view", tag, "--repo", REPO, "--json", "isLatest"]
        ).stdout
    )
    if view.get("isLatest") is not True:
        raise ValueError("tag is not the latest GitHub release")


def _ensure_release(tag: str) -> None:
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
            "--draft",
            "--title",
            tag,
            "--notes",
            f"Pending native release {tag}",
        ]
    )


def _upload(tag: str, path: Path, name: str) -> None:
    assets = _asset_map(tag)
    if name in assets:
        if assets[name].get("size") == path.stat().st_size:
            return
        raise ValueError(f"release asset already exists with different size: {name}")
    _run(["gh", "release", "upload", tag, str(path), "--repo", REPO])


def _asset_map(tag: str) -> dict:
    raw = _run(["gh", "release", "view", tag, "--repo", REPO, "--json", "assets"])
    return {row["name"]: row for row in json.loads(raw.stdout).get("assets", [])}


def _verify_http_asset(asset: dict, digest: str, size: int) -> None:
    _verify_http(asset["url"], digest, size)


def _verify_http(url: str, digest: str, size: int) -> None:
    request = urllib.request.Request(
        url, headers={"User-Agent": "ooxml-native-release"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}: {url}")
    if size and len(payload) != size:
        raise ValueError(f"HTTP size mismatch: {url}")
    if digest and hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError(f"HTTP sha256 mismatch: {url}")


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
