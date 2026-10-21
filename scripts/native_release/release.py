"""Full public native release orchestration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .artifacts import attach_notarization, create_artifacts
from .builder import build_stage
from .config import ConfigError
from .evidence import EvidenceSeal
from .functional import run_functional
from .input_lock import verify_inputs
from .license_gate import validate_release_license
from .manifest import build_manifest
from .publish import release_target, run_external_transaction
from .reproducibility import collect_attestation, normalized_payload_sha256, sha256_file
from .scan import ScanError, scan_dmg, scan_zip
from .signing import (
    notarize_artifacts,
    release_credentials,
    sign_disk_image,
    sign_payload,
    strip_payload,
    verify_gatekeeper,
    verify_payload_signatures,
)


def run_release(config: dict[str, Any], stage_dir: str | None) -> dict[str, Any]:
    creds = release_credentials(config)
    license_summary = validate_release_license(
        _required_env(config["entitlement"]["e2e_license_env"]), config
    )
    _require_clean_sources(config)
    wheelhouse = _wheelhouse(config)
    inputs = verify_inputs(config, wheelhouse)
    target_commit = release_target(config)
    evidence = EvidenceSeal(_run_dir(config) / "evidence")
    stage = _stage(stage_dir, _run_dir(config))
    build_stage(config, stage, "release")
    _require_stage(stage)
    strip_payload(stage)
    pre_sign_hash = normalized_payload_sha256(stage, normalize_macho=False)
    sign_payload(stage, creds.identity)
    team_id = verify_payload_signatures(stage, require_team=True)
    artifacts = create_artifacts(stage, _run_dir(config) / "artifacts", config)
    evidence.write(
        "signing-payload.json",
        {
            "team_id": team_id,
            "pre_sign_payload_sha256": pre_sign_hash,
            "path": str(stage),
        },
    )
    return _finish_release(
        config,
        stage,
        artifacts,
        creds,
        team_id,
        pre_sign_hash,
        license_summary,
        inputs,
        evidence,
        wheelhouse,
        target_commit,
    )


def _finish_release(
    config,
    stage,
    artifacts,
    creds,
    team_id,
    pre_sign_hash,
    license_summary,
    inputs,
    evidence,
    wheelhouse,
    target_commit,
):
    artifacts = _notarize(config, artifacts, creds, team_id, evidence)
    verify_gatekeeper(
        Path(artifacts["dmg"]["path"]), stage / "bin/ooxml", stage / "bin/ooxml-engine"
    )
    manifest = build_manifest(config, artifacts, team_id)
    scan, zip_scan = _scan_artifacts(config, artifacts, evidence)
    functional = _run_all_functional(config, artifacts, evidence)
    attestation = _attest(config, stage, wheelhouse, pre_sign_hash, artifacts, evidence)
    prepublish = {
        "status": "ready_to_publish",
        "mode": "release",
        "license": license_summary,
        "team_id": team_id,
        "manifest": manifest,
        "scan": scan,
        "zip_scan": zip_scan,
        "attestation": attestation,
        "functional": functional,
        "inputs": inputs,
        "release_commit": target_commit,
    }
    prepublish_seal = evidence.finalize_prepublish(prepublish)
    publish_result = run_external_transaction(
        config, manifest, artifacts, _run_dir(config) / "public-manifest.json"
    )
    result = {**prepublish, "status": "ok", "publish": publish_result}
    receipt = _write_postpublish_receipt(evidence, publish_result, prepublish_seal)
    result["evidence"] = {
        "prepublish": prepublish_seal,
        "postpublish_receipt": receipt,
    }
    return result


def _write_postpublish_receipt(evidence, publish_result, prepublish_seal):
    payload = {
        "schema_version": 1,
        "status": "published",
        "publish": publish_result,
        "prepublish_seal": prepublish_seal,
    }
    try:
        path = evidence.write("postpublish-receipt.json", payload)
    except OSError as exc:
        return {"status": "failed", "error": str(exc)}
    return {"status": "recorded", "path": str(path)}


def _notarize(config, artifacts, creds, team_id, evidence):
    sign_disk_image(Path(artifacts["dmg"]["path"]), creds.identity)
    notary = notarize_artifacts(
        Path(artifacts["dmg"]["path"]),
        Path(artifacts["zip"]["path"]),
        creds.notary_profile,
        config,
    )
    artifacts = attach_notarization(artifacts, notary)
    for row in artifacts.values():
        path = Path(row["path"])
        row["sha256"] = sha256_file(path)
        row["size"] = path.stat().st_size
    _write_candidate_metadata(artifacts, team_id)
    evidence.write(
        "signing-notarization.json",
        {"team_id": team_id, "notarization": notary, "artifacts": artifacts},
    )
    return artifacts


def _scan_artifacts(config, artifacts, evidence):
    scan = scan_dmg(Path(artifacts["dmg"]["path"]), config)
    zip_scan = scan_zip(Path(artifacts["zip"]["path"]), config)
    if not scan["pass"] or not zip_scan["pass"]:
        raise ScanError("final signed artifact scan failed")
    evidence.write("scan.json", {"dmg": scan, "zip": zip_scan})
    return scan, zip_scan


def _run_all_functional(config, artifacts, evidence):
    dmg = run_functional(
        Path(artifacts["dmg"]["path"]), config, evidence.root / "dmg", False
    )
    zip = run_functional(
        Path(artifacts["zip"]["path"]), config, evidence.root / "zip", False
    )
    return {"dmg": dmg["pass"], "zip": zip["pass"]}


def _attest(config, stage, wheelhouse, pre_sign_hash, artifacts, evidence):
    hashes = {
        kind: {"sha256": row["sha256"], "size": row["size"]}
        for kind, row in artifacts.items()
    }
    attestation = collect_attestation(
        config, Path(config["_repo_root"]), wheelhouse, stage, pre_sign_hash, hashes
    )
    evidence.write("build-attestation.json", attestation)
    return attestation


def _write_candidate_metadata(artifacts, team_id):
    for row in artifacts.values():
        metadata = {
            "team_id": team_id,
            "sha256": row["sha256"],
            "size": row["size"],
            "notarization": row["notarization"],
        }
        path = Path(row["path"]).with_suffix(Path(row["path"]).suffix + ".json")
        path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def _require_clean_sources(config):
    root = Path(config["_repo_root"])
    dirty = []
    for repo in [root, *(root / path for path in config["sources"].values())]:
        result = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or result.stdout.strip():
            dirty.append(str(repo))
    if dirty:
        raise ConfigError(f"release requires clean repositories: {', '.join(dirty)}")


def _wheelhouse(config):
    value = _required_env(config["build"]["wheelhouse_env"])
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise ConfigError(f"wheelhouse does not exist: {path}")
    return path


def _stage(stage_dir, run_dir):
    return Path(stage_dir or run_dir / "stage").expanduser().resolve()


def _run_dir(config):
    root = (
        Path(config["_repo_root"]).parent
        / ".delivery-evidence/artifacts/native/release"
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def _require_stage(path):
    if not path.is_dir() or not any(path.iterdir()):
        raise ConfigError(f"native build adapter produced no stage: {path}")


def _required_env(name):
    value = __import__("os").environ.get(name, "")
    if not value:
        raise ConfigError(f"{name} is required")
    return value
