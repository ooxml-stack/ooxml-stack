"""Fixtures shared by the shared-runner contract and execution tests.

These build real Git repositories and real plan files. Nothing here starts
Docker: the container seam is replaced by each test, so what is under test is the
runner's own decision-making.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

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
    return {{"image": "fixture@sha256:" + "0" * 64, "platform": "linux/amd64",
            "timeout_seconds": 30, "stage_timeout_seconds": 5}}


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


def _init_repo(repo):
    snapshot.git(repo, "init", "--quiet")
    for key, value in (("user.email", "ci@example.invalid"), ("user.name", "CI fixture"),
                       ("commit.gpgsign", "false"), ("core.hooksPath", "/dev/null")):
        snapshot.git(repo, "config", key, value)
    snapshot.git(repo, "add", ".")
    snapshot.git(repo, "commit", "--quiet", "-m", "fixture")
    return repo


def make_repo(tmp_path, name=REPO, stages=("alpha", "beta"), adapter=ADAPTER_SOURCE):
    repo = tmp_path / name
    (repo / "ci").mkdir(parents=True)
    (repo / "scripts/ci").mkdir(parents=True)
    (repo / "ci/environment.json").write_text(json.dumps({"schema_version": 1}))
    (repo / "scripts/ci/__init__.py").write_text("")
    if adapter is not None:
        (repo / "scripts/ci/adapter.py").write_text(adapter.format(stages=list(stages)))
    return _init_repo(repo)


# An adapter whose behaviour comes from a sibling module in the same repository.
# ``scripts.ci.helper`` is the module whose provenance the loader has to control:
# the calling checkout has one of the same name.
HELPER_ADAPTER_SOURCE = '''
"""Fixture adapter that depends on a sibling module."""

from scripts.ci import helper


def describe(root):
    return {"stages": list(helper.STAGES), "environment": {"image": "fixture@sha256:" + "0" * 64},
            "implementation": helper.NAME, "static_commands": [], "runtime_steps": []}


def load_config(root):
    return {"image": "fixture@sha256:" + "0" * 64, "platform": "linux/amd64",
            "timeout_seconds": 30, "stage_timeout_seconds": 5, "helper": helper.NAME}


def input_hashes(root):
    return {}


def is_dirty(root):
    return False


def operations(root, reports, config):
    return {name: (lambda name=name: {"stage": name}) for name in helper.STAGES}


def verify_report(report, commit, config, inputs):
    if report.get("image") != config["image"]:
        raise ValueError("image mismatch")
    if report.get("helper") != helper.NAME:
        raise ValueError("report was not produced by this helper")
'''


def helper_source(name, stages):
    return f"NAME = {name!r}\nSTAGES = {list(stages)!r}\n"


def make_helper_repo(tmp_path, name, stages, helper_name=None, adapter=HELPER_ADAPTER_SOURCE):
    """A repository whose adapter behaviour is decided by ``scripts.ci.helper``."""
    repo = tmp_path / name
    (repo / "ci").mkdir(parents=True)
    (repo / "scripts/ci").mkdir(parents=True)
    (repo / "ci/environment.json").write_text(json.dumps({"schema_version": 1}))
    (repo / "scripts/ci/__init__.py").write_text("")
    (repo / "scripts/ci/helper.py").write_text(helper_source(helper_name or name, stages))
    (repo / "scripts/ci/adapter.py").write_text(adapter)
    return _init_repo(repo)


def rewrite_helper(repo, name, stages):
    (repo / "scripts/ci/helper.py").write_text(helper_source(name, stages))


def commit_all(repo, message="fixture"):
    snapshot.git(repo, "add", ".")
    snapshot.git(repo, "commit", "--quiet", "-m", message)
    return snapshot.git(repo, "rev-parse", "HEAD")


def _input_manifest(tmp_path, inputs):
    """Path strings get their real digest; a mapping lets a test force drift."""
    manifest = []
    for item in inputs:
        if isinstance(item, dict):
            manifest.append({"path": item["path"], "sha256": item["sha256"]})
            continue
        path = tmp_path / item
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "0" * 64
        manifest.append({"path": item, "sha256": digest})
    return manifest


def make_plan(tmp_path, repo, *, adapter="scripts.ci.adapter", nodes=None, diagnostics=(),
              full=None, inputs=(), digest="a" * 64, key=REPO, name="plan.json"):
    payload = {
        "schema_version": 1, "inputs_digest": digest, "inputs": _input_manifest(tmp_path, inputs),
        "diagnostics": list(diagnostics),
        "nodes": nodes if nodes is not None else [{"key": key}],
        "full": {key: {"workflow": ".github/workflows/ci.yml", "jobs": [{"id": "check"}],
                       **({"adapter": adapter} if adapter else {})}} if full is None else full,
    }
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return path


def expected_for(repo, plan, stages=("alpha", "beta"), key=REPO, commit=None):
    """The expectations a verifier re-derives from the request, never from a report."""
    loaded = plan_module.load(plan)
    resolved = commit or snapshot.resolve_commit(repo, "HEAD")
    return {"repository": key, "commit": resolved,
            "runner_commit": RUNNER_COMMIT,
            "runner_source_sha256": identity.source_sha256_at(identity.PACKAGE_DIR.parent, RUNNER_COMMIT),
            "plan_sha256": loaded["sha256"], "inputs_digest": loaded["inputs_digest"],
            "inputs_reverified": plan_module.reverify_inputs(
                loaded, Path(plan).parent, key, resolved),
            "binding": plan_module.binding_for(loaded, key), "stages": list(stages)}


def passing_report(repo, plan, stages=("alpha", "beta"), **overrides):
    loaded = plan_module.load(plan)
    commit = overrides.pop("commit", snapshot.resolve_commit(repo, "HEAD"))
    payload = {
        "schema_version": 1, "status": "pass", "repository": overrides.pop("repository", REPO),
        "commit": commit,
        "runner": {"commit": RUNNER_COMMIT, "source_sha256": identity.identity()["source_sha256"]},
        "plan": {"path": loaded["path"], "sha256": loaded["sha256"],
                 "inputs_digest": loaded["inputs_digest"],
                 "inputs_reverified": overrides.pop("inputs_reverified", plan_module.reverify_inputs(
                     loaded, Path(plan).parent, REPO, commit))},
        "binding": overrides.pop("binding", plan_module.binding_for(loaded, REPO)),
        "image": "fixture@sha256:" + "0" * 64, "inputs": {}, "exit_code": 0,
        "stages": [{"name": name, "status": "pass"} for name in stages],
    }
    payload.update(overrides)
    return payload