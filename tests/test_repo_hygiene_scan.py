from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import repo_hygiene_scan
from repo_hygiene_scan import classify_paths, lfs_policy, raw_release_evidence_hits, redact_secret, secret_matches


def test_redact_secret_removes_local_path_and_token_value() -> None:
    prefix = "/" + "Users/"
    key = "api" + "_key"
    value = "token" + "-secret-value"
    line = f'{key}="{prefix}touchskyer/.local/{value}"'

    redacted = redact_secret(line)

    assert prefix not in redacted
    assert value not in redacted
    assert "<redacted>" in redacted


def test_secret_matches_reports_redacted_preview_only() -> None:
    auth = "Bearer " + "abcdefghijklmnopqrstuvwxyz1234567890"
    text = f"Authorization: {auth}"

    matches = secret_matches(text, ["release-evidence/example.json"])

    assert matches == [{"type": "bearer_token", "preview": "Authorization: Bearer <redacted>"}]


def test_secret_matches_flags_env_paths_without_values() -> None:
    matches = secret_matches("SAFE=value", [".env"])

    assert matches == [{"type": "env_path", "preview": ".env"}]


def test_classify_paths_groups_large_evidence_families() -> None:
    assert classify_paths(["release-evidence/run/rows.jsonl"]) == "jsonl_ledger_evidence"
    assert classify_paths(["release-evidence/run/output.pptx"]) == "office_package_evidence"
    assert classify_paths(["release-evidence/run/summary.json"]) == "json_evidence"


def test_raw_release_evidence_hits_skips_deleted_tracked_files(tmp_path: Path, monkeypatch) -> None:
    existing = tmp_path / "release-evidence/run/summary.json"
    existing.parent.mkdir(parents=True)
    existing.write_text('{"ok": true}\n', encoding="utf-8")

    def fake_git(root: Path, *args: str, **kwargs: object) -> str:
        assert root == tmp_path
        return "\n".join(["release-evidence/run/deleted.json", "release-evidence/run/summary.json"])

    monkeypatch.setattr(repo_hygiene_scan, "git", fake_git)

    assert raw_release_evidence_hits(tmp_path) == []


def test_lfs_policy_ignores_deleted_and_empty_evidence_files(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".gitattributes").write_text("release-evidence/**/*.jsonl filter=lfs diff=lfs merge=lfs -text\n")
    release_dir = tmp_path / "release-evidence/run"
    release_dir.mkdir(parents=True)
    (release_dir / "empty.jsonl").write_text("", encoding="utf-8")
    (release_dir / "rows.jsonl").write_text('{"row": 1}\n', encoding="utf-8")

    def fake_git(root: Path, *args: str, **kwargs: object) -> str:
        assert root == tmp_path
        if args == ("lfs", "ls-files", "-n"):
            return ""
        if args == ("lfs", "status", "--porcelain"):
            return ""
        return "\n".join([
            "release-evidence/run/deleted.jsonl",
            "release-evidence/run/empty.jsonl",
            "release-evidence/run/rows.jsonl",
        ])

    monkeypatch.setattr(repo_hygiene_scan, "git", fake_git)

    assert lfs_policy(tmp_path)["current_files_should_be_lfs_but_are_not"] == ["release-evidence/run/rows.jsonl"]
