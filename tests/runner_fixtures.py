"""Fixtures shared by the shared-runner contract and execution tests.

These build real Git repositories and real plan files. Nothing here starts
Docker: the container seam is replaced by each test, so what is under test is the
runner's own decision-making.
"""

from __future__ import annotations

import json

from ooxml_runner import identity, snapshot
from ooxml_runner import plan as plan_module

REPO = "ooxml-operation-engine"
RUNNER_COMMIT = identity.identity()["commit"]

ADAPTER_SOURCE = '''
"""Fixture adapter."""

STAGES = {stages!r}


def describe(root):
    return {{"stages": list(STAGES), "environment": {{"image": "fixture@sha256:" + "0" * 64}},
            "implementation": "fixture", "static_commands": [],
            "runtime_steps": [{{"stage": name, "resolved_at": "runtime"}} for name in STAGES]}}


def load_config(root):
    return {{"image": "fixture@sha256:" + "0" * 64, "stage_timeout_seconds": 5}}


def input_hashes(root):
    return {{}}


def is_dirty(root):
    return False


def operations(root, reports, config):
    return {{name: (lambda name=name: {{"stage": name}}) for name in STAGES}}


def verify_report(report, commit, config, inputs):
    if report.get("image") != config["image"]:
        raise ValueError("image mismatch")
    if report.get("inputs") != inputs:
        raise ValueError("input mismatch")
'''


def make_repo(tmp_path, name=REPO, stages=("alpha", "beta"), adapter=ADAPTER_SOURCE):
    repo = tmp_path / name
    (repo / "ci").mkdir(parents=True)
    (repo / "scripts/ci").mkdir(parents=True)
    (repo / "ci/environment.json").write_text(json.dumps({"schema_version": 1}))
    (repo / "scripts/ci/__init__.py").write_text("")
    if adapter is not None:
        (repo / "scripts/ci/adapter.py").write_text(adapter.format(stages=list(stages)))
    snapshot.git(repo, "init", "--quiet")
    for key, value in (("user.email", "ci@example.invalid"), ("user.name", "CI fixture"),
                       ("commit.gpgsign", "false"), ("core.hooksPath", "/dev/null")):
        snapshot.git(repo, "config", key, value)
    snapshot.git(repo, "add", ".")
    snapshot.git(repo, "commit", "--quiet", "-m", "fixture")
    return repo


def make_plan(tmp_path, repo, *, adapter="scripts.ci.adapter", nodes=None, diagnostics=(),
              full=None, inputs=(), digest="a" * 64):
    payload = {
        "schema_version": 1, "inputs_digest": digest, "inputs": list(inputs),
        "diagnostics": list(diagnostics),
        "nodes": nodes if nodes is not None else [{"key": REPO}],
        "full": {REPO: {"workflow": ".github/workflows/ci.yml", "jobs": [{"id": "check"}],
                        **({"adapter": adapter} if adapter else {})}} if full is None else full,
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(payload))
    return path


def expected_for(repo, plan, stages=("alpha", "beta")):
    loaded = plan_module.load(plan)
    return {"repository": REPO, "commit": snapshot.resolve_commit(repo, "HEAD"),
            "runner_commit": RUNNER_COMMIT, "plan_sha256": loaded["sha256"],
            "inputs_digest": loaded["inputs_digest"], "stages": list(stages)}


def passing_report(repo, plan, stages=("alpha", "beta"), **overrides):
    loaded = plan_module.load(plan)
    payload = {
        "schema_version": 1, "status": "pass", "repository": REPO,
        "commit": snapshot.resolve_commit(repo, "HEAD"),
        "runner": {"commit": RUNNER_COMMIT, "source_sha256": identity.identity()["source_sha256"]},
        "plan": {"path": loaded["path"], "sha256": loaded["sha256"],
                 "inputs_digest": loaded["inputs_digest"]},
        "image": "fixture@sha256:" + "0" * 64, "inputs": {}, "exit_code": 0,
        "stages": [{"name": name, "status": "pass"} for name in stages],
    }
    payload.update(overrides)
    return payload