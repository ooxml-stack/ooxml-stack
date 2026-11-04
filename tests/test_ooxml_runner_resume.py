"""

# pyright: reportMissingImports=falseVerified stage resume and focused pytest evidence tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ooxml_runner import container, report as report_module, resume


def _report(stages, *, status="fail", runner=None, inputs=None):
    return {
        "schema_version": report_module.REPORT_SCHEMA_VERSION,
        "status": status,
        "repository": "ooxml-operation-engine",
        "commit": "a" * 40,
        "runner": runner or {"commit": "b" * 40, "source_sha256": "c" * 64},
        "plan": {"sha256": "d" * 64, "inputs_digest": "e" * 64},
        "binding": {"workflow": ".github/workflows/ci.yml", "jobs": ["default"],
                    "adapter": "scripts.ci.adapter"},
        "image": "fixture@sha256:" + "0" * 64,
        "inputs": inputs or {"ci/environment.json": "1" * 64},
        "started_at": "2026-11-04T00:00:00+00:00",
        "finished_at": None,
        "exit_code": None,
        "stages": [{"name": name, "status": "not_run"} for name in stages],
    }


def test_resume_reuses_success_prefix_and_reruns_failed_and_downstream(tmp_path):
    stages = ["environment", "dependencies", "tests"]
    previous = _report(stages)
    previous["stages"][0].update(status="pass", details={"a": 1}, artifacts=["a.log"])
    previous["stages"][1].update(status="fail", error="fixture")
    previous["status"] = "fail"
    previous["exit_code"] = 1
    source = tmp_path / "prior" / "report.json"
    source.parent.mkdir()
    report_module.save(source.parent, previous)
    current = _report(stages, status="running")
    destination = tmp_path / "current"
    destination.mkdir()

    plan = resume.prepare(previous, current, source, destination)

    assert plan["reused_stages"] == ["environment"]
    assert plan["rerun_stages"] == ["dependencies", "tests"]
    assert current["stages"][0]["reused"] is True
    assert current["stages"][1]["status"] == "not_run"
    assert current["stages"][2]["status"] == "not_run"
    assert json.loads((destination / "resume.json").read_text())["failed_stage"] == "dependencies"


def test_stage_protocol_skips_only_a_verified_reused_prefix(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    report = _report(("alpha", "beta"), status="running")
    report["stages"][0].update(status="pass", reused=True, reused_from="/prior")
    calls = []
    steps = {"alpha": lambda: calls.append("alpha"), "beta": lambda: calls.append("beta")}

    container.run_stages(reports, steps, report, 5)

    assert calls == ["beta"]
    assert report["stages"][0]["status"] == "pass"
    assert report["stages"][1]["status"] == "pass"


@pytest.mark.parametrize("field,value", [
    ("commit", "f" * 40),
    ("runner", {"commit": "f" * 40, "source_sha256": "c" * 64}),
    ("inputs", {"ci/environment.json": "f" * 64}),
])
def test_resume_refuses_identity_drift(tmp_path, field, value):
    stages = ["environment", "tests"]
    previous = _report(stages)
    previous["stages"][0]["status"] = "pass"
    previous["stages"][1]["status"] = "fail"
    current = _report(stages, status="running")
    current[field] = value
    source = tmp_path / "prior" / "report.json"
    source.parent.mkdir()
    report_module.save(source.parent, previous)
    destination = tmp_path / "current"
    destination.mkdir()

    with pytest.raises(resume.ResumeError, match="differs"):
        resume.prepare(previous, current, source, destination)


def test_resume_records_only_failed_pytest_nodes(tmp_path):
    stages = ["tests"]
    previous = _report(stages)
    previous["stages"][0]["status"] = "fail"
    source = tmp_path / "prior" / "report.json"
    source.parent.mkdir()
    report_module.save(source.parent, previous)
    (source.parent / "pytest.json").write_text(json.dumps({
        "collected": ["test_a.py::ok", "test_b.py::bad"],
        "results": [
            {"nodeid": "test_a.py::ok", "outcome": "passed"},
            {"nodeid": "test_b.py::bad", "outcome": "failed"},
        ],
    }))
    current = _report(stages, status="running")
    destination = tmp_path / "current"
    destination.mkdir()

    plan = resume.prepare(previous, current, source, destination)

    assert plan["failed_nodes"] == ["test_b.py::bad"]