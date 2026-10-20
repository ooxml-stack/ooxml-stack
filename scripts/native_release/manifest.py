"""Construct and validate artifact-complete public manifests."""

from __future__ import annotations

import re
from typing import Any

SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    """The public manifest is incomplete or inconsistent."""


def build_manifest(
    config: dict[str, Any], artifacts: dict[str, dict[str, Any]], signing_team_id: str
) -> dict[str, Any]:
    runtime = config["runtime"]
    publish = config["publish"]
    rendered = {}
    for kind, artifact_config in config["artifacts"].items():
        row = artifacts.get(kind)
        if row is None:
            raise ManifestError(f"missing artifact result for {kind}")
        digest = _digest(row.get("sha256"), kind)
        url = _versioned_url(
            publish, runtime["client_version"], digest, artifact_config["filename"]
        )
        rendered[kind] = {
            "url": url,
            "checksum_url": f"{url}.sha256",
            "filename": artifact_config["filename"],
            "sha256": digest,
            "size": _size(row.get("size"), kind),
            "cache": artifact_config["immutable_cache"],
            "notarization": dict(row["notarization"]),
            "page_visible": bool(artifact_config["page_visible"]),
        }
    manifest = {
        "schema_version": 1,
        "product": "ooxml",
        "client_version": runtime["client_version"],
        "engine_version": runtime["engine_version"],
        "artifact_id": runtime["artifact_id"],
        "architecture": config["target"]["architecture"],
        "min_macos": config["target"]["minimum_version"],
        "runtime_classification": runtime["classification"],
        "fully_native": runtime["fully_native"],
        "embedded_python_runtime": config["build"]["embedded_python_runtime"],
        "external_python_required": runtime["external_python_required"],
        "pdf_readability": runtime["pdf_readability"],
        "license_required": config["entitlement"]["license_required"],
        "entitlement_url": config["entitlement"]["entitlement_url"],
        "signing_team_id": signing_team_id,
        "notarization_status": _notarization_status(rendered),
        "notary_request_id": _notary_request_id(rendered),
        "artifacts": rendered,
        "latest": {
            "manifest_url": publish["latest_manifest_url"],
            "cache": publish["latest_cache"],
        },
    }
    validate_manifest(manifest, config)
    return manifest


def validate_manifest(manifest: dict[str, Any], config: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "product",
        "client_version",
        "engine_version",
        "artifact_id",
        "architecture",
        "min_macos",
        "runtime_classification",
        "fully_native",
        "embedded_python_runtime",
        "external_python_required",
        "pdf_readability",
        "license_required",
        "entitlement_url",
        "signing_team_id",
        "notarization_status",
        "notary_request_id",
        "artifacts",
        "latest",
    }
    missing = sorted(required - set(manifest))
    if missing:
        raise ManifestError(f"manifest missing fields: {', '.join(missing)}")
    if manifest["fully_native"] is not False:
        raise ManifestError("manifest must not claim fully native")
    if set(manifest["artifacts"]) != {"dmg", "zip"}:
        raise ManifestError("manifest must contain DMG and ZIP artifacts")
    for name, row in manifest["artifacts"].items():
        _validate_artifact(name, row, config)
    dmg = manifest["artifacts"]["dmg"]
    if dmg["page_visible"] is not True or "/latest/" in dmg["url"]:
        raise ManifestError("page-visible DMG must use an immutable versioned URL")
    if manifest["notarization_status"] != "notarized":
        raise ManifestError("both artifacts must be notarized before release")


def _validate_artifact(name: str, row: dict[str, Any], config: dict[str, Any]) -> None:
    for field in (
        "url",
        "checksum_url",
        "filename",
        "sha256",
        "size",
        "cache",
        "notarization",
    ):
        if field not in row:
            raise ManifestError(f"artifact {name} missing {field}")
    if not str(row["url"]).startswith("https://") or "/latest/" in row["url"]:
        raise ManifestError(f"artifact {name} URL must be immutable HTTPS")
    if row["checksum_url"] != f"{row['url']}.sha256":
        raise ManifestError(f"artifact {name} checksum URL mismatch")
    if not SHA256.fullmatch(row["sha256"]):
        raise ManifestError(f"artifact {name} has invalid sha256")
    if not isinstance(row["size"], int) or row["size"] <= 0:
        raise ManifestError(f"artifact {name} has invalid size")
    expected = config["artifacts"][name]
    if row["filename"] != expected["filename"]:
        raise ManifestError(f"artifact {name} filename mismatch")
    if row["notarization"].get("status") != "notarized":
        raise ManifestError(f"artifact {name} is not notarized")


def _versioned_url(
    publish: dict[str, Any], version: str, digest: str, filename: str
) -> str:
    base = publish["base_url"].rstrip("/")
    return f"{base}/{version}/{digest}/{filename}"


def _digest(value: Any, kind: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ManifestError(f"artifact {kind} has invalid sha256")
    return value


def _size(value: Any, kind: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ManifestError(f"artifact {kind} has invalid size")
    return value


def _notarization_status(artifacts: dict[str, dict[str, Any]]) -> str:
    statuses = {row["notarization"].get("status") for row in artifacts.values()}
    return "notarized" if statuses == {"notarized"} else "failed"


def _notary_request_id(artifacts: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        kind: str(row["notarization"].get("request_id", ""))
        for kind, row in artifacts.items()
    }
