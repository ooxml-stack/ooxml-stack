"""Verify product page, latest manifest, and versioned artifacts agree."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from .manifest import validate_manifest


class LiveVerifyError(ValueError):
    """A live release surface is inconsistent."""


def verify_live(config: dict[str, Any]) -> dict[str, Any]:
    page = _text(config["publish"]["product_page_url"])
    latest = json.loads(_read(config["publish"]["latest_manifest_url"]))
    validate_manifest(latest, config)
    dmg = latest["artifacts"]["dmg"]
    versioned = json.loads(_read(dmg["url"].rsplit("/", 1)[0] + "/manifest.json"))
    if versioned != latest:
        raise LiveVerifyError("latest manifest differs from versioned manifest")
    if latest["client_version"] not in page or dmg["sha256"] not in page:
        raise LiveVerifyError(
            "product page does not display the latest version and DMG SHA-256"
        )
    return {"page": config["publish"]["product_page_url"], "latest": latest}


def _read(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "ooxml-native-release"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise LiveVerifyError(f"HTTP {response.status}: {url}")
        return response.read()


def _text(url: str) -> str:
    return _read(url).decode("utf-8", "replace")
