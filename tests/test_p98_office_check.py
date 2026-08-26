from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_p98_office_check as office


def test_office_check_blocks_without_automation_permission(tmp_path, monkeypatch) -> None:
    # The host lacks macOS Automation consent, so check_open must record a
    # blocker instead of a fake pass.
    p = tmp_path / "sample.docx"
    p.write_bytes(b"fake")
    monkeypatch.setattr(office, "automation_permission_ok", lambda app: False)

    result = office.check_open(p, poll_seconds=1)

    assert result["status"] == "blocked_automation_permission"
    assert result["loaded"] is False
    assert "consent" in result.get("detail", "").lower()


def test_check_open_unknown_extension() -> None:
    result = office.check_open(Path("/tmp/x.pdf"), poll_seconds=1)
    assert result["status"] == "unsupported_extension"


def test_app_registry_covers_common_extensions() -> None:
    assert office.APP_BY_EXT[".docx"] == "Microsoft Word"
    assert office.APP_BY_EXT[".pptx"] == "Microsoft PowerPoint"
    assert office.APP_BY_EXT[".xlsx"] == "Microsoft Excel"
    assert office.COUNT_QUERY["Microsoft Word"] == "count of documents"