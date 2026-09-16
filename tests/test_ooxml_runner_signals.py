"""Real termination signals must reach the same finalization path as Ctrl-C.

Python's default SIGTERM handling terminates the process outright: no exception
is raised, no ``finally`` runs and no ``atexit`` hook is called. A run stopped
by a task manager therefore left its report at ``running`` forever and never
removed its container. SIGINT already worked because it raises
``KeyboardInterrupt``.

These tests drive the real ``python -m ooxml_runner run`` process and replace
only the Docker transport, so the signal really is delivered by the operating
system to the process that owns the report.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from runner_fixtures import REPO, RUNNER_COMMIT, make_plan, make_repo

from ooxml_runner import report as report_module

ROOT = Path(__file__).resolve().parents[1]

TRANSPORT = '''
import os, pathlib, sys, time
base = pathlib.Path(__file__).resolve().parents[1]
if sys.argv[1] == "info":
    print(1)
elif sys.argv[1] == "rm":
    (base / "cleanup.called").write_text("called")
elif sys.argv[1] == "run":
    sys.stdin.readline()
    (base / "ready").write_text("ready")
    time.sleep(30)
'''


def _transport(tmp_path):
    directory = tmp_path / "bin"
    directory.mkdir()
    fake = directory / "docker"
    fake.write_text("#!" + sys.executable + "\n" + TRANSPORT)
    fake.chmod(0o755)
    return directory


def _start(tmp_path, repo, plan, output):
    env = {**os.environ, "PATH": str(_transport(tmp_path)) + os.pathsep + os.environ["PATH"],
           "PYTHONPATH": str(ROOT), "OOXML_STACK_TOKEN": "fixture-token"}
    argv = [sys.executable, "-m", "ooxml_runner", "run", "--root", str(tmp_path), "--repo", REPO,
            "--commit", "HEAD", "--runner-commit", RUNNER_COMMIT, "--plan", str(plan),
            "--output", str(output)]
    return subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, start_new_session=True)


def _interrupt(tmp_path, repo, plan, output, signum):
    """Start the real CLI, wait for the transport, deliver ``signum``, return state."""
    process = _start(tmp_path, repo, plan, output)
    try:
        deadline = time.monotonic() + 60
        while not (tmp_path / "ready").exists():
            assert process.poll() is None, process.stdout.read()
            assert time.monotonic() < deadline, "the CLI never reached the transport"
            time.sleep(0.05)
        process.send_signal(signum)
        process.wait(timeout=60)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=30)
    path = next(output.glob("*/*/report.json"), None)
    assert path is not None, "the run left no report at all"
    events = path.parent / "progress.jsonl"
    return {
        "report": report_module.load(path),
        "events": ([json.loads(line)["event"] for line in events.read_text().splitlines()]
                   if events.exists() else []),
        "cleanup_called": (tmp_path / "cleanup.called").exists(),
    }


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_a_real_termination_signal_leaves_a_finished_failure_report(tmp_path, signum):
    repo = make_repo(tmp_path)
    plan = make_plan(tmp_path, repo)
    output = tmp_path / "out"

    observed = _interrupt(tmp_path, repo, plan, output, signum)

    assert observed["report"]["status"] == "fail"
    assert observed["report"]["finished_at"]
    assert observed["report"]["exit_code"] == 1
    assert observed["cleanup_called"], "the container was never cleaned up"
    assert observed["events"].count("gate_failed") == 1