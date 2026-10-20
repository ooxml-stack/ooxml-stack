"""Developer ID signing and notarization gates."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SigningError(ValueError):
    """Signing, notarization, or Gatekeeper validation failed."""


@dataclass(frozen=True)
class ReleaseCredentials:
    identity: str
    notary_profile: str


def release_credentials(config: dict[str, Any], env=None) -> ReleaseCredentials:
    values = os.environ if env is None else env
    signing = config["signing"]
    notary = config["notarization"]
    identity = values.get(signing["identity_env"], "")
    profile = values.get(notary["keychain_profile_env"], "")
    if not identity.startswith(signing["identity_prefix"]):
        raise SigningError(
            f"{signing['identity_env']} must select a Developer ID Application identity"
        )
    if not profile:
        raise SigningError(f"{notary['keychain_profile_env']} is required")
    listed = _run(["security", "find-identity", "-v", "-p", "codesigning"]).stdout
    if identity not in listed:
        raise SigningError(
            "configured Developer ID identity is not available in the keychain"
        )
    _run(["xcrun", "--find", "notarytool"])
    return ReleaseCredentials(identity=identity, notary_profile=profile)


def macho_files(root: str | Path) -> list[Path]:
    paths = []
    for path in Path(root).rglob("*"):
        if path.is_file() and not path.is_symlink() and _is_macho(path):
            paths.append(path)
    return sorted(paths, key=lambda item: len(item.parts), reverse=True)


def strip_payload(root: str | Path) -> list[Path]:
    stripped = macho_files(root)
    for path in stripped:
        _run(["strip", "-x", str(path)])
    return stripped


def sign_payload(root: str | Path, identity: str) -> list[Path]:
    signed = macho_files(root)
    for path in signed:
        _run(
            [
                "codesign",
                "--force",
                "--options",
                "runtime",
                "--timestamp",
                "--sign",
                identity,
                str(path),
            ]
        )
    return signed


def ad_hoc_sign_payload(root: str | Path) -> list[Path]:
    signed = macho_files(root)
    for path in signed:
        _run(["codesign", "--force", "--sign", "-", str(path)])
    return signed


def verify_payload_signatures(root: str | Path, require_team: bool = True) -> str:
    team_ids = set()
    for path in macho_files(root):
        _run(["codesign", "--verify", "--strict", "--verbose=4", str(path)])
        details = _run(
            ["codesign", "-dv", "--verbose=4", str(path)], check=False
        ).stderr
        team = _field(details, "TeamIdentifier")
        if team:
            team_ids.add(team)
    if require_team and len(team_ids) != 1:
        raise SigningError("signed payload must have exactly one TeamIdentifier")
    if require_team and "not set" in team_ids:
        raise SigningError("ad-hoc signature is not allowed for public release")
    return next(iter(team_ids), "")


def sign_disk_image(path: Path, identity: str) -> None:
    _run(["codesign", "--force", "--timestamp", "--sign", identity, str(path)])


def notarize_artifacts(
    dmg: Path, zip_path: Path, profile: str, config: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    results = {
        "dmg": _submit_notary(dmg, profile),
        "zip": _submit_notary(zip_path, profile),
    }
    if results["dmg"]["status"] != "Accepted" or results["zip"]["status"] != "Accepted":
        raise SigningError("notarization was not accepted")
    if config["notarization"]["dmg"]["staple"]:
        _run(["xcrun", "stapler", "staple", str(dmg)])
        _run(["xcrun", "stapler", "validate", str(dmg)])
    results["dmg"]["stapled"] = True
    results["zip"]["stapled"] = False
    results["zip"]["mode"] = config["notarization"]["zip"]["mode"]
    return results


def verify_gatekeeper(dmg: Path, client: Path, engine: Path) -> None:
    with tempfile.TemporaryDirectory() as folder:
        quarantined = Path(folder) / dmg.name
        shutil.copy2(dmg, quarantined)
        _run(
            [
                "xattr",
                "-w",
                "com.apple.quarantine",
                "0081;00000000;Safari;00000000-0000-0000-0000-000000000000",
                str(quarantined),
            ]
        )
        _run(["spctl", "-a", "-vv", "-t", "open", str(quarantined)])
    _run(["spctl", "-a", "-vv", "-t", "exec", str(client)])
    _run(["spctl", "-a", "-vv", "-t", "exec", str(engine)])


def _submit_notary(path: Path, profile: str) -> dict[str, Any]:
    result = _run(
        [
            "xcrun",
            "notarytool",
            "submit",
            str(path),
            "--keychain-profile",
            profile,
            "--wait",
            "--output-format",
            "json",
        ]
    )
    payload = json.loads(result.stdout)
    status = payload.get("status")
    request_id = payload.get("id")
    if not status or not request_id:
        raise SigningError(f"notarytool returned incomplete response for {path.name}")
    return {"status": status, "request_id": request_id}


def _is_macho(path: Path) -> bool:
    result = _run(["file", "-b", str(path)], check=False)
    return "Mach-O" in result.stdout


def _field(text: str, name: str) -> str:
    for line in text.splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    return ""


def _run(command: list[str], check: bool = True):
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SigningError(f"{' '.join(command)} failed: {detail}")
    return result
