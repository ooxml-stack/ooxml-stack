"""Pure result payload builders for native release orchestration."""

from __future__ import annotations


def local_result(prepublish, seal):
    return {
        **prepublish,
        "status": "ok",
        "mode": "release-local",
        "publish": {"status": "skipped", "reason": "no-publish"},
        "evidence": {"prepublish": seal},
    }


def prepublish_payload(
    license_summary,
    team_id,
    manifest,
    scan,
    zip_scan,
    attestation,
    functional,
    inputs,
    target_commit,
):
    return {
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
