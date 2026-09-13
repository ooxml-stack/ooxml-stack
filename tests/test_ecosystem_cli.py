"""CLI acceptance tests: ``--write`` / ``--check`` verdicts and scan persistence."""

from __future__ import annotations

import json

from ecosystem_fixtures import (
    PINNED_SHA,
    _docx_lock,
    _docx_pyproject,
    build_workspace,
    resolvable_for,
    seal,
    write,
)
from ecosystem_workflows import (
    WORKFLOW_DOCX_FLOATING,
    WORKFLOW_ENV_EDGE_CASES,
    WORKFLOW_ENV_NESTED,
    WORKFLOW_TWO_ORGS,
    WORKFLOW_TWO_ORGS_REVERSED,
)
from scripts.ooxml_ci import cli, gitfacts

SCAN_RELPATH = "ooxml-stack/ci/reports/scan.json"
PLAN_RELPATH = "ooxml-stack/ci/ecosystem-plan.json"


def test_write_then_check_is_stable(tmp_path, capsys, monkeypatch):
    root = build_workspace(tmp_path)
    resolvable_for(monkeypatch, seal(root))
    assert cli.main(["--write", "--root", str(root)]) == 0
    capsys.readouterr()
    assert cli.main(["--check", "--root", str(root)]) == 0
    assert "result        : ok" in capsys.readouterr().out


def test_commented_and_block_env_values_survive_write_and_check(tmp_path, capsys, monkeypatch):
    """End-to-end: YAML comments, escapes and block chomping reach the committed plan."""
    root = build_workspace(tmp_path)
    resolvable_for(monkeypatch, seal(root))
    write(root / "ooxml-core/.github/workflows/full.yml", WORKFLOW_ENV_EDGE_CASES)
    assert cli.main(["--write", "--root", str(root)]) == 0
    capsys.readouterr()
    plan = json.loads((root / PLAN_RELPATH).read_text(encoding="utf-8"))
    env = plan["full"]["ooxml-core"]["jobs"][0]["env"]
    assert env["OPTIONS"] == "a,b"
    assert env["EXPRESSION"] == "${{ format('{0},{1}', github.sha, github.ref) }}"
    assert env["FOLDED"] == "--first --second"
    assert env["LITERAL"] == "first\nsecond\n"
    assert env["STRIPPED"] == "first\nsecond"
    assert env["TRAILING"] == "a,b"
    assert env["BLOCK_COMMENT"] == "first\nsecond"
    steps = plan["full"]["ooxml-core"]["jobs"][0]["steps"]
    assert steps[2]["env"] == {"UV_PYTHON": "3.10"}
    assert steps[3]["env"] == {"MESSAGE": 'say "hello,world"', "OTHER": "ok"}
    assert cli.main(["--check", "--root", str(root)]) == 0


def test_check_fails_on_an_unsupported_workflow_structure(tmp_path, capsys, monkeypatch):
    root = build_workspace(tmp_path)
    resolvable_for(monkeypatch, seal(root))
    write(root / "ooxml-core/.github/workflows/full.yml", WORKFLOW_ENV_NESTED)
    assert cli.main(["--write", "--root", str(root)]) == 0
    capsys.readouterr()
    assert cli.main(["--check", "--root", str(root)]) == 1
    assert "unsupported_workflow" in capsys.readouterr().out


def test_check_fails_when_the_plan_is_missing(tmp_path, capsys, monkeypatch):
    root = build_workspace(tmp_path)
    resolvable_for(monkeypatch, seal(root))
    assert cli.main(["--check", "--root", str(root)]) == 1
    assert "plan is missing" in capsys.readouterr().out


def test_check_detects_an_uncommitted_pin_change(tmp_path, capsys, monkeypatch):
    root = build_workspace(tmp_path)
    resolvable_for(monkeypatch, seal(root))
    assert cli.main(["--write", "--root", str(root)]) == 0
    write(root / "python-docx/pyproject.toml", _docx_pyproject(core_ref="v0.6.1"))
    capsys.readouterr()
    assert cli.main(["--check", "--root", str(root)]) == 1
    assert "differs" in capsys.readouterr().out


def test_write_refuses_when_a_full_sha_cannot_be_verified(tmp_path, capsys, monkeypatch):
    """A full SHA is a required fact: ls-remote cannot prove it, so it must be fetched or local."""
    root = build_workspace(tmp_path)
    heads = seal(root)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\nversion = "1.2.0"\n'
        f'dependencies = ["ooxml-core @ git+https://github.com/ooxml-stack/ooxml-core.git@{PINNED_SHA}"]\n',
    )
    write(
        root / "python-docx/uv.lock",
        _docx_lock(PINNED_SHA, heads["ooxml-test-framework"], core_ref=PINNED_SHA),
    )
    resolvable_for(monkeypatch, heads)
    assert cli.main(["--write", "--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "unverifiable" in out
    assert not (root / PLAN_RELPATH).exists()


def test_write_accepts_a_sha_that_exists_locally(tmp_path, capsys, monkeypatch):
    root = build_workspace(tmp_path)
    heads = seal(root)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\nversion = "1.2.0"\n'
        f'dependencies = ["ooxml-core @ git+https://github.com/ooxml-stack/ooxml-core.git@{heads["ooxml-core"]}"]\n',
    )
    write(
        root / "python-docx/uv.lock",
        _docx_lock(heads["ooxml-core"], heads["ooxml-test-framework"], core_ref=heads["ooxml-core"]),
    )
    resolvable_for(monkeypatch, heads)
    assert cli.main(["--write", "--root", str(root)]) == 0


def test_write_refuses_when_the_remote_is_unreachable(tmp_path, capsys, monkeypatch):
    root = build_workspace(tmp_path)
    seal(root)
    monkeypatch.setattr(gitfacts, "remote_refs", lambda *a, **k: {"ok": False, "error": "unreachable"})
    assert cli.main(["--write", "--root", str(root)]) == 1
    assert "unverifiable" in capsys.readouterr().out


def test_write_does_not_overwrite_an_existing_plan_on_measurement_failure(tmp_path, capsys, monkeypatch):
    root = build_workspace(tmp_path)
    resolvable_for(monkeypatch, seal(root))
    assert cli.main(["--write", "--root", str(root)]) == 0
    committed = (root / PLAN_RELPATH).read_text(encoding="utf-8")
    capsys.readouterr()
    monkeypatch.setattr(gitfacts, "remote_refs", lambda *a, **k: {"ok": False, "error": "unreachable"})
    assert cli.main(["--write", "--root", str(root)]) == 1
    assert (root / PLAN_RELPATH).read_text(encoding="utf-8") == committed


def test_strict_upgrades_warnings_to_failures(tmp_path, capsys, monkeypatch):
    root = build_workspace(tmp_path)
    resolvable_for(monkeypatch, seal(root))
    assert cli.main(["--write", "--root", str(root)]) == 0
    capsys.readouterr()
    assert cli.main(["--check", "--root", str(root)]) == 0
    capsys.readouterr()
    assert cli.main(["--check", "--strict", "--root", str(root)]) == 1
    assert "version_skew" in capsys.readouterr().out


def test_check_persists_the_current_scan_and_reason(tmp_path, capsys, monkeypatch):
    """A failing ``--check`` must refresh scan.json, not leave the last --write result."""
    root = build_workspace(tmp_path)
    resolvable_for(monkeypatch, seal(root))
    assert cli.main(["--write", "--root", str(root)]) == 0
    scan_path = root / SCAN_RELPATH
    healthy = json.loads(scan_path.read_text(encoding="utf-8"))
    assert "check" not in healthy
    capsys.readouterr()
    monkeypatch.setattr(gitfacts, "remote_refs", lambda *a, **k: {"ok": False, "error": "network down"})
    assert cli.main(["--check", "--root", str(root)]) == 1
    refreshed = json.loads(scan_path.read_text(encoding="utf-8"))
    assert refreshed["check"]["result"] == "failed"
    assert any("unverifiable" in problem for problem in refreshed["check"]["problems"])
    assert refreshed["diagnostic_counts"] != healthy["diagnostic_counts"]


def test_check_offline_still_reports_a_ci_ref(tmp_path, capsys, monkeypatch):
    """The offline path must not silently skip workflow ``uses:`` refs."""
    root = build_workspace(tmp_path)
    heads = seal(root)
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_DOCX_FLOATING)
    resolvable_for(monkeypatch, heads)
    assert cli.main(["--write", "--root", str(root)]) == 0
    capsys.readouterr()
    assert cli.main(["--check", "--offline", "--strict", "--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "unverifiable" in out
    assert "ci.yml" in out


def test_check_strict_rejects_a_local_version_violating_a_public_constraint(tmp_path, capsys, monkeypatch):
    """``1.0+local`` must not satisfy ``!=1.0``; the violating lock must fail."""
    root = build_workspace(tmp_path)
    heads = seal(root)
    write(
        root / "python-docx/pyproject.toml",
        '[project]\nname = "python-docx"\nversion = "1.2.0"\n'
        'dependencies = ["ooxml-core!=1.0"]\n\n'
        "[tool.uv.sources]\n"
        'ooxml-core = { git = "https://github.com/ooxml-stack/ooxml-core.git", tag = "v1.0" }\n',
    )
    write(
        root / "python-docx/uv.lock",
        "[[package]]\n"
        'name = "ooxml-core"\n'
        'version = "1.0+local"\n'
        f'source = {{ git = "https://github.com/ooxml-stack/ooxml-core.git?tag=v1.0#{heads["ooxml-core"]}" }}\n',
    )
    resolvable_for(monkeypatch, heads)
    assert cli.main(["--write", "--root", str(root)]) == 0
    capsys.readouterr()
    assert cli.main(["--check", "--strict", "--root", str(root)]) == 1
    assert "constraint_violation" in capsys.readouterr().out


def test_check_strict_is_order_independent_for_two_same_named_repos(tmp_path, capsys, monkeypatch):
    """The verdict must not depend on which of two same-named declarations comes first."""
    codes = []
    for index, workflow in enumerate((WORKFLOW_TWO_ORGS, WORKFLOW_TWO_ORGS_REVERSED)):
        root = build_workspace(tmp_path / str(index))
        heads = seal(root)
        write(root / "python-docx/.github/workflows/ci.yml", workflow)

        def fake(remote_url, cwd, timeout, cache, _heads=heads):
            if "other-org" in remote_url:
                return {"ok": True, "tags": {}, "peeled": {}, "heads": {}}
            return {"ok": True, "tags": {"v1.0.0": _heads["ooxml-stack"]}, "peeled": {}, "heads": {}}

        monkeypatch.setattr(gitfacts, "remote_refs", fake)
        assert cli.main(["--write", "--root", str(root)]) == 0
        capsys.readouterr()
        codes.append(cli.main(["--check", "--strict", "--root", str(root)]))
        capsys.readouterr()
    assert codes == [1, 1]