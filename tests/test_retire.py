from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import retire

PAST = "2026-01-01T00:00:00Z"
FUTURE = "2999-01-01T00:00:00Z"


def _make_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / ".delivery-evidence" / "retire-registry").mkdir(parents=True)
    return ws


def _make_sessions(tmp_path: Path, status: str) -> Path:
    flow = tmp_path / "fakehome" / ".opc" / "sessions" / "root1" / "flowA"
    run_dir = flow / "nodes" / "n1" / "run_1"
    run_dir.mkdir(parents=True)
    (flow / "flow-state.json").write_text(json.dumps({"status": status}), encoding="utf-8")
    return run_dir


def _entry(path: Path, expires: str = PAST, **extra) -> str:
    rec = {
        "ts": "2026-01-01T00:00:00Z",
        "kind": "run-artifact",
        "path": str(path),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "ttl_days": 14,
        "expires_at": expires,
        "session": "flowA",
        "node": "n1",
        "run": "run_1",
    }
    rec.update(extra)
    return json.dumps(rec)


def _write_ledger(ws: Path, lines: list[str]) -> None:
    (ws / ".delivery-evidence" / "retire-registry" / "registry.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _run(ws: Path, tmp_path: Path, *extra: str) -> dict:
    argv = [
        "--workspace",
        str(ws),
        "--managed-root",
        str(tmp_path / "fakehome" / ".opc" / "sessions"),
        *extra,
    ]
    assert retire.main(argv) == 0


def test_dry_run_is_default_and_deletes_nothing(tmp_path) -> None:
    ws = _make_workspace(tmp_path)
    run_dir = _make_sessions(tmp_path, "completed")
    artifact = run_dir / "artifact.txt"
    artifact.write_text("data", encoding="utf-8")
    _write_ledger(ws, [_entry(artifact)])

    _run(ws, tmp_path)

    assert artifact.is_file()
    assert not (ws / ".delivery-evidence" / "retire-registry" / "gc-manifests").exists()


def test_execute_deletes_expired_and_keeps_everything_else(tmp_path) -> None:
    ws = _make_workspace(tmp_path)
    run_dir = _make_sessions(tmp_path, "completed")
    expired = run_dir / "expired.txt"
    expired.write_text("old", encoding="utf-8")
    fresh = run_dir / "fresh.txt"
    fresh.write_text("new", encoding="utf-8")
    _write_ledger(ws, [_entry(expired), _entry(fresh, expires=FUTURE)])

    _run(ws, tmp_path, "--execute")

    assert not expired.exists()
    assert fresh.is_file()
    assert not (run_dir / "expired.txt").exists()
    manifests = list((ws / ".delivery-evidence" / "retire-registry" / "gc-manifests").glob("gc-*.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert len(manifest["deletions"]["removed"]) == 1
    assert manifest["deletions"]["removed"][0]["path"] == str(expired)
    assert len(manifest["deletions"]["candidates"]) == 1


def test_execute_removes_only_now_empty_run_dirs(tmp_path) -> None:
    ws = _make_workspace(tmp_path)
    flow = tmp_path / "fakehome" / ".opc" / "sessions" / "root1" / "flowA"
    run_dir = flow / "nodes" / "n1" / "run_1"
    run_dir.mkdir(parents=True)
    (flow / "flow-state.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    artifact = run_dir / "only.txt"
    artifact.write_text("data", encoding="utf-8")
    _write_ledger(ws, [_entry(artifact)])

    _run(ws, tmp_path, "--execute")

    assert not artifact.exists()
    assert not run_dir.exists()
    assert (flow / "flow-state.json").is_file()


def test_skip_reasons_cover_every_guard(tmp_path) -> None:
    ws = _make_workspace(tmp_path)
    ledger_dir = ws / ".delivery-evidence" / "retire-registry"
    completed_run = _make_sessions(tmp_path, "completed")
    active_run = tmp_path / "fakehome" / ".opc" / "sessions" / "root1" / "flowB" / "nodes" / "n" / "run_1"
    active_run.mkdir(parents=True)
    (active_run.parents[2] / "flow-state.json").write_text(
        json.dumps({"status": "in_progress"}), encoding="utf-8"
    )
    (active_run / "a.txt").write_text("active", encoding="utf-8")
    symlink_path = completed_run / "link.txt"
    os.symlink(completed_run / "target.txt", symlink_path)
    (completed_run / "target.txt").write_text("real", encoding="utf-8")
    git_file = ws / "repo" / ".git" / "objects" / "x"
    git_file.parent.mkdir(parents=True)
    git_file.write_text("git", encoding="utf-8")
    ledger_file = ledger_dir / "last-run.json"
    ledger_file.write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside" / "x.txt"
    outside.parent.mkdir(parents=True)
    outside.write_text("out", encoding="utf-8")

    lines = [
        _entry(symlink_path),
        _entry(git_file),
        _entry(ledger_file),
        _entry(outside),
        _entry(active_run / "a.txt"),
        _entry(completed_run / "gone.txt"),
        _entry(completed_run / "target.txt", expires="not-a-date"),
        _entry(completed_run / "target.txt"),
    ]
    lines.append("{broken json")
    _write_ledger(ws, lines)

    _run(ws, tmp_path, "--execute")

    assert symlink_path.is_symlink()
    assert (completed_run / "target.txt").is_file()
    assert git_file.is_file()
    assert ledger_file.is_file()
    assert outside.is_file()
    manifests = list((ledger_dir / "gc-manifests").glob("gc-*.json"))
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    reasons = {s["reason"] for s in manifest["deletions"]["skipped"]}
    assert reasons == {
        "symlink-refused",
        "git-internals-refused",
        "ledger-exempt",
        "outside-managed-roots",
        "session-not-completed",
        "bad-expires-at",
        "duplicate-entry",
    }
    assert len(manifest["deletions"]["already_missing"]) == 1
    assert manifest["ledger"]["torn_lines"] == 1
    assert manifest["deletions"]["removed"] == []


def test_compaction_triggers_only_above_threshold(tmp_path) -> None:
    ws = _make_workspace(tmp_path)
    ledger = ws / ".delivery-evidence" / "retire-registry" / "registry.jsonl"
    run_dir = _make_sessions(tmp_path, "completed")
    lines = [
        _entry(run_dir / f"f{i}.txt", expires=PAST if i < 2 else FUTURE) for i in range(4)
    ]
    _write_ledger(ws, lines)
    for i in range(4):
        (run_dir / f"f{i}.txt").write_text("x", encoding="utf-8")

    _run(ws, tmp_path, "--execute", "--compact-threshold", "999999")
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 4

    _run(ws, tmp_path, "--execute", "--compact-threshold", "3")
    kept = ledger.read_text(encoding="utf-8").splitlines()
    assert len(kept) == 2
    for line in kept:
        assert json.loads(line)["expires_at"] == FUTURE


def test_tripwire_baseline_then_alarm(tmp_path) -> None:
    ws = _make_workspace(tmp_path)
    legacy = ws / ".delivery-evidence" / "legacy-task"
    legacy.mkdir()
    (legacy / "old.txt").write_text("legacy", encoding="utf-8")

    _run(ws, tmp_path)  # dry run must not create the baseline
    baseline = ws / ".delivery-evidence" / "retire-registry" / "tripwire-baseline.json"
    assert not baseline.exists()

    _run(ws, tmp_path, "--execute")
    assert baseline.is_file()
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    assert payload["grandfathered_count"] == 1

    new_task = ws / ".delivery-evidence" / "new-task"
    new_task.mkdir()
    (new_task / "new.txt").write_text("new", encoding="utf-8")

    assert retire.main(
        [
            "--workspace",
            str(ws),
            "--managed-root",
            str(tmp_path / "fakehome" / ".opc" / "sessions"),
            "--execute",
            "--json",
            "--fail-on-alarm",
        ]
    ) == 3


def test_missing_ledger_and_missing_dirs_are_handled(tmp_path) -> None:
    ws = tmp_path / "empty-ws"
    (ws / ".delivery-evidence" / "retire-registry").mkdir(parents=True)
    _run(ws, tmp_path, "--execute")
    manifests = list((ws / ".delivery-evidence" / "retire-registry" / "gc-manifests").glob("gc-*.json"))
    assert len(manifests) == 1
