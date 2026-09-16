"""Terminal progress events must leave a strictly parseable stream.

``container.fail`` writes the report before it announces it, so a failed
announcement can leave a terminal report with no terminal event. The host
completes the event - but a write interrupted before its newline leaves a partial
record, and appending the recovery event directly merged the two into one
unparseable line.

Every reader of ``progress.jsonl`` parses each line strictly; the diagnostics
gate does exactly that. The stream therefore has to be repaired, not merely
tolerated. The torn bytes are audit evidence, so they are copied verbatim into a
sidecar *before* the main file is touched, and the main file is only truncated
once that copy is durable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from runner_fixtures import ADAPTER_SOURCE, REPO, RUNNER_COMMIT, make_plan, make_repo

from ooxml_runner import container
from ooxml_runner import report as report_module

ROOT = Path(__file__).resolve().parents[1]
TORN = b'{"event":"gate_failed"'
FAILING_ADAPTER = ADAPTER_SOURCE.replace(
    'return {{name: (lambda name=name: {{"stage": name}}) for name in STAGES}}',
    'return {{name: (lambda: 1 / 0) for name in STAGES}}',
)

CONTAINER = '''
import os, pathlib, sys
if sys.argv[1] == "info":
    print(1)
    raise SystemExit(0)
if sys.argv[1] == "rm":
    raise SystemExit(0)
sys.stdin.readline()
mounts = {}
for index, arg in enumerate(sys.argv):
    if arg == "--env":
        key, value = sys.argv[index + 1].split("=", 1)
        if key == "OOXML_CI_RUNNER_COMMIT":
            os.environ[key] = value
    if arg == "--mount":
        values = dict(part.split("=", 1) for part in sys.argv[index + 1].split(",") if "=" in part)
        mounts[values["target"]] = values["source"]
from ooxml_runner import container, entry
real_event = container.progress_event

def one_event_fails(reports, event, **fields):
    if event == "gate_failed":
        with (pathlib.Path(reports) / "progress.jsonl").open("a") as stream:
            stream.write('{"event":"gate_failed"')
        raise OSError("terminal event write failed after a partial write")
    real_event(reports, event, **fields)

container.progress_event = one_event_fails
raise SystemExit(entry.main(["--repository", "ooxml-operation-engine",
                             "--adapter", "scripts.ci.adapter",
                             "--root", str(pathlib.Path(mounts["/input"]) / "ooxml-operation-engine"),
                             "--reports", mounts["/reports"]]))
'''


def _failed_report(reports, error="ZeroDivisionError: division by zero"):
    payload = report_module.new_report(repository=REPO, commit="0" * 40, runner={}, plan={},
                                       binding={}, image="fixture", inputs={}, stages=["one"])
    payload["stages"][0].update(status="fail", error=error)
    payload.update(status="fail", exit_code=1, finished_at=report_module.utc_now(), error=error)
    report_module.save(reports, payload)
    return payload


def _strict_events(reports):
    """Parse every line. A single unparseable line is a failure, not a skip."""
    path = Path(reports) / report_module.PROGRESS_NAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _torn_stream(reports, payload, *, lead=()):
    for event in lead:
        report_module.progress_event(reports, event, commit="0" * 40)
    with (reports / report_module.PROGRESS_NAME).open("ab") as stream:
        stream.write(TORN)
    return payload


def _recover(reports, payload, times=1):
    for _ in range(times):
        container.finalize_host_failure(reports, payload, container.ContainerError("exit 1", 1))


def _only_report(output):
    path = next(Path(output).glob("*/*/report.json"))
    return report_module.load(path), path.parent


# --- the recovery contract ----------------------------------------------------

def test_a_saved_failure_without_its_terminal_event_gets_one(tmp_path):
    reports = tmp_path / "reports"
    payload = _failed_report(reports)

    _recover(reports, payload)

    assert [event["event"] for event in _strict_events(reports)] == ["gate_failed"]
    assert report_module.load(reports)["error"] == "ZeroDivisionError: division by zero"


def test_a_torn_terminal_event_is_quarantined_before_the_recovery_event(tmp_path):
    """The reviewed case: a half-written event must not swallow the recovery."""
    reports = tmp_path / "reports"
    payload = _torn_stream(reports, _failed_report(reports), lead=("gate_started",))

    _recover(reports, payload)

    # Strict: no line is skipped, and the terminal event is its own record.
    assert [event["event"] for event in _strict_events(reports)] == ["gate_started", "gate_failed"]
    assert (reports / report_module.TORN_NAME).read_bytes() == TORN + b"\n"
    assert report_module.load(reports)["error"] == "ZeroDivisionError: division by zero"


def test_repeated_recovery_keeps_exactly_one_terminal_event(tmp_path):
    reports = tmp_path / "reports"
    payload = _torn_stream(reports, _failed_report(reports), lead=("gate_started",))

    _recover(reports, payload, times=3)

    assert [event["event"] for event in _strict_events(reports)] == ["gate_started", "gate_failed"]
    assert (reports / report_module.TORN_NAME).read_bytes() == TORN + b"\n"


def test_a_complete_event_without_a_trailing_newline_is_not_quarantined(tmp_path):
    """A whole record that lost only its newline is already durable."""
    reports = tmp_path / "reports"
    payload = _failed_report(reports)
    complete = json.dumps({"schema_version": 1, "event": "gate_failed",
                           "error": "ZeroDivisionError: division by zero"}).encode()
    (reports / report_module.PROGRESS_NAME).write_bytes(complete)

    _recover(reports, payload, times=2)

    assert not (reports / report_module.TORN_NAME).exists()
    assert [event["event"] for event in _strict_events(reports)] == ["gate_failed"]


def test_a_failed_sidecar_write_leaves_the_stream_untouched(tmp_path):
    """If the torn bytes cannot be preserved, nothing is repaired or lost."""
    reports = tmp_path / "reports"
    payload = _torn_stream(reports, _failed_report(reports), lead=("gate_started",))
    path = reports / report_module.PROGRESS_NAME
    before = path.read_bytes()
    (reports / report_module.TORN_NAME).mkdir()  # a directory cannot be appended to

    with pytest.raises(OSError):
        _recover(reports, payload)

    assert path.read_bytes() == before
    assert report_module.load(reports)["error"] == "ZeroDivisionError: division by zero"


# --- the same guarantee through the real entry --------------------------------

def _transport(tmp_path):
    directory = tmp_path / "bin"
    directory.mkdir()
    fake = directory / "docker"
    fake.write_text("#!" + sys.executable + "\n" + CONTAINER)
    fake.chmod(0o755)
    return directory


def test_a_partial_terminal_write_through_the_real_entry_is_recovered(tmp_path):
    """Real host CLI -> local transport -> real ``entry.main``, torn at the end."""
    repo = make_repo(tmp_path, adapter=FAILING_ADAPTER)
    plan = make_plan(tmp_path, repo)
    output = tmp_path / "out"
    env = {**os.environ, "PATH": str(_transport(tmp_path)) + os.pathsep + os.environ["PATH"],
           "PYTHONPATH": str(ROOT), "OOXML_STACK_TOKEN": "fixture-token"}
    argv = [sys.executable, "-m", "ooxml_runner", "run", "--root", str(tmp_path), "--repo", REPO,
            "--commit", "HEAD", "--runner-commit", RUNNER_COMMIT, "--plan", str(plan),
            "--output", str(output)]

    process = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True,
                   timeout=180, check=False)

    assert process.returncode != 0
    payload, reports = _only_report(output)
    assert payload["status"] == "fail"
    assert "ZeroDivisionError" in payload["error"]
    events = [event["event"] for event in _strict_events(reports)]  # strict, no skipping
    assert events.count("gate_failed") == 1
    assert (reports / report_module.TORN_NAME).read_bytes() == TORN + b"\n"


def test_the_runner_bookkeeping_is_not_a_stage_artifact(tmp_path):
    """The sidecar is the runner's own file, not something a stage produced."""
    reports = tmp_path / "reports"
    reports.mkdir()
    before = set(os.listdir(reports))
    (reports / report_module.PROGRESS_NAME).write_text("")
    (reports / report_module.TORN_NAME).write_text("")
    (reports / "stage-output.txt").write_text("")

    assert container._artifacts(reports, before) == ["stage-output.txt"]