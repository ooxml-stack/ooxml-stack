"""Verify product page, latest manifest, and versioned artifacts agree."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .manifest import validate_manifest

PAGE_MANIFEST_MODE = "manifest-v1"
PAGE_MODE_META = "ooxml-native-release-mode"


class LiveVerifyError(ValueError):
    """A live release surface is inconsistent."""


class _PageContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.tokens: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "meta":
            name = values.get("name", "").lower()
            if name:
                self.meta[name] = values.get("content", "")
        self.tokens.extend(values.values())

    def handle_data(self, data: str) -> None:
        self.tokens.append(data)


def verify_page_contract(page: str, manifest: dict[str, Any]) -> dict[str, str]:
    parser = _PageContractParser()
    parser.feed(page)
    if parser.meta.get(PAGE_MODE_META) != PAGE_MANIFEST_MODE:
        raise LiveVerifyError(
            "page blocker: product page does not declare "
            f'{PAGE_MODE_META}="{PAGE_MANIFEST_MODE}"'
        )
    manifest_url = manifest["latest"]["manifest_url"]
    if manifest_url not in "\n".join(parser.tokens):
        raise LiveVerifyError(
            "page blocker: product page does not consume the expected latest "
            f"manifest URL: {manifest_url}"
        )
    return {"mode": PAGE_MANIFEST_MODE, "manifest_url": manifest_url}


def verify_page_contract_url(url: str, manifest: dict[str, Any]) -> dict[str, str]:
    return verify_page_contract(_text(url), manifest)


def verify_page_manifest_api(url: str, manifest: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ooxml-native-release", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        status = response.status
        payload = response.read()
        content_type = response.headers.get("Content-Type", "")
        cache_control = response.headers.get("Cache-Control", "")
    if status != 200:
        raise LiveVerifyError(f"page manifest API HTTP {status}: {url}")
    if "application/json" not in content_type.lower():
        raise LiveVerifyError(f"page manifest API content-type mismatch: {url}")
    if "no-store" not in cache_control.lower():
        raise LiveVerifyError(
            f"page manifest API cache-control must include no-store: {url}"
        )
    try:
        actual = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveVerifyError(f"page manifest API JSON is invalid: {url}") from exc
    if actual != manifest:
        raise LiveVerifyError(
            f"page manifest API does not match latest manifest: {url}"
        )
    return {
        "url": url,
        "status": status,
        "content_type": content_type,
        "cache_control": cache_control,
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def verify_artifact_url(
    url: str, digest: str, size: int, *, kind: str
) -> dict[str, Any]:
    status, payload = fetch_url(url)
    actual = hashlib.sha256(payload).hexdigest()
    if len(payload) != size:
        raise LiveVerifyError(f"HTTP size mismatch: {url}")
    if actual != digest:
        raise LiveVerifyError(f"HTTP sha256 mismatch: {url}")
    return {
        "kind": kind,
        "url": url,
        "status": status,
        "size": len(payload),
        "sha256": actual,
    }


def verify_content_url(url: str, expected: bytes, *, kind: str) -> dict[str, Any]:
    status, payload = fetch_url(url)
    if payload != expected:
        raise LiveVerifyError(f"HTTP content mismatch: {url}")
    return {
        "kind": kind,
        "url": url,
        "status": status,
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def verify_json_url(url: str, expected: dict[str, Any], *, kind: str) -> dict[str, Any]:
    status, payload = fetch_url(url)
    try:
        actual = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveVerifyError(f"HTTP JSON is invalid: {url}") from exc
    if actual != expected:
        raise LiveVerifyError(f"HTTP JSON mismatch: {url}")
    return {
        "kind": kind,
        "url": url,
        "status": status,
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def verify_live(config: dict[str, Any]) -> dict[str, Any]:
    latest_url = config["publish"]["latest_manifest_url"]
    latest = _json(latest_url)
    validate_manifest(latest, config)
    versioned_url = (
        latest["artifacts"]["dmg"]["url"].rsplit("/", 1)[0] + "/manifest.json"
    )
    versioned = _json(versioned_url)
    if latest != versioned:
        raise LiveVerifyError(
            "latest manifest does not exactly match the versioned manifest"
        )
    artifacts = []
    for kind, row in versioned["artifacts"].items():
        artifacts.append(_verify_artifact(kind, row["url"], row))
        artifacts.append(_verify_checksum(kind, row["checksum_url"], row))
        latest_url = config["publish"]["latest_artifact_url_template"].format(
            filename=row["filename"]
        )
        artifacts.append(_verify_artifact(f"{kind}-latest", latest_url, row))
        latest_checksum_url = config["publish"]["latest_artifact_url_template"].format(
            filename=f"{row['filename']}.sha256"
        )
        artifacts.append(_verify_checksum(f"{kind}-latest", latest_checksum_url, row))
    page = verify_page_contract_url(config["publish"]["product_page_url"], versioned)
    page_api = verify_page_manifest_api(
        config["publish"]["page_manifest_api_url"], versioned
    )
    return {
        "page": config["publish"]["product_page_url"],
        "page_contract": page,
        "page_manifest_api": page_api,
        "latest": versioned,
        "artifacts": artifacts,
    }


def _verify_artifact(kind: str, url: str, row: dict[str, Any]) -> dict[str, Any]:
    payload = _read(url)
    digest = hashlib.sha256(payload).hexdigest()
    if len(payload) != row["size"] or digest != row["sha256"]:
        raise LiveVerifyError(f"{kind} artifact content mismatch: {url}")
    return {"kind": kind, "url": url, "size": len(payload), "sha256": digest}


def _verify_checksum(kind: str, url: str, row: dict[str, Any]) -> dict[str, Any]:
    payload = _read(url)
    expected = f"{row['sha256']}  {row['filename']}\n".encode("utf-8")
    if payload != expected:
        raise LiveVerifyError(f"{kind} checksum content mismatch: {url}")
    return {"kind": f"{kind}-checksum", "url": url, "size": len(payload)}


def _json(url: str) -> dict[str, Any]:
    try:
        payload = json.loads(_read(url))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveVerifyError(f"invalid JSON: {url}") from exc
    if not isinstance(payload, dict):
        raise LiveVerifyError(f"JSON root is not an object: {url}")
    return payload


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checksum_payload(row: dict[str, Any]) -> bytes:
    return f"{row['sha256']}  {row['filename']}\n".encode("utf-8")


def fetch_url(url: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "ooxml-native-release"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        status = response.status
        payload = response.read()
    if status != 200:
        raise LiveVerifyError(f"HTTP {status}: {url}")
    return status, payload


def _read(url: str) -> bytes:
    return fetch_url(url)[1]


def _text(url: str) -> str:
    return _read(url).decode("utf-8", "replace")
