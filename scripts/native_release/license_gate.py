"""Validate external test entitlements without retaining their contents."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed25519
except ImportError:  # pragma: no cover - fail at use, not import time
    InvalidSignature = None
    ed25519 = None

REQUIRED_FIELDS = {
    "schema_version",
    "license_id",
    "license_type",
    "licensee",
    "product_id",
    "artifact_id",
    "not_before",
    "expiry",
    "signature",
}


class LicenseGateError(ValueError):
    """The external test entitlement is not acceptable for release testing."""


def validate_release_license(
    path: str | Path, config: dict[str, Any], today=None
) -> dict[str, Any]:
    source = Path(path).expanduser()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LicenseGateError(f"cannot read release-test license: {exc}") from exc
    entitlement = config["entitlement"]
    runtime = config["runtime"]
    _validate_fields(payload, entitlement, runtime)
    _validate_dates(payload, today or date.today())
    _verify_signature(payload, entitlement["activation_public_key_hex"])
    return {
        "license_id": payload["license_id"],
        "license_type": payload["license_type"],
        "licensee": payload["licensee"],
        "artifact_id": payload["artifact_id"],
        "not_before": payload["not_before"],
        "expiry": payload["expiry"],
    }


def _validate_fields(
    payload: dict[str, Any], entitlement: dict[str, Any], runtime: dict[str, Any]
) -> None:
    missing = sorted(REQUIRED_FIELDS - set(payload))
    if missing:
        raise LicenseGateError(f"license missing fields: {', '.join(missing)}")
    if payload["schema_version"] != 1:
        raise LicenseGateError("license schema_version must be 1")
    if payload["artifact_id"] != runtime["artifact_id"]:
        raise LicenseGateError("license artifact_id does not match release artifact")
    if payload["product_id"] != "ooxml-operation-engine":
        raise LicenseGateError("license product_id is invalid")
    if payload["license_type"] not in entitlement["allowed_license_types"]:
        raise LicenseGateError("license_type is not allowed for release testing")
    if payload["license_id"] in entitlement["forbidden_license_ids"]:
        raise LicenseGateError("license_id is forbidden for public release testing")
    licensee = str(payload["licensee"]).casefold()
    forbidden = entitlement.get("forbidden_licensee_markers", [])
    if any(marker.casefold() in licensee for marker in forbidden):
        raise LicenseGateError("licensee is internal-only")


def _validate_dates(payload: dict[str, Any], today: date) -> None:
    try:
        not_before = date.fromisoformat(payload["not_before"])
        expiry = date.fromisoformat(payload["expiry"])
    except (TypeError, ValueError) as exc:
        raise LicenseGateError("license dates must be ISO-8601 dates") from exc
    if not_before > today:
        raise LicenseGateError("license is not active yet")
    if expiry < today:
        raise LicenseGateError("license has expired")


def _verify_signature(payload: dict[str, Any], public_key_hex: str) -> None:
    if ed25519 is None or InvalidSignature is None:
        raise LicenseGateError(
            "cryptography package is required for license verification"
        )
    signature = payload.get("signature")
    try:
        signature_bytes = bytes.fromhex(signature)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(public_key_hex)
        )
        public_key.verify(signature_bytes, _canonical_payload(payload))
    except (TypeError, ValueError, InvalidSignature) as exc:
        raise LicenseGateError("license signature is invalid") from exc


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in payload.items() if key != "signature"}
    return json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
