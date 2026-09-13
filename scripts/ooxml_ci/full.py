"""Static binding from each declared full plan to its workflow jobs and steps.

This proves the declared workflow and job exist and records their steps. It does
not prove that a shell command means the same thing at runtime.
"""

from __future__ import annotations

from typing import Any

from .facts import Facts
from .inputs import node_index


def _error(code: str, where: str, detail: str) -> dict[str, Any]:
    return {"code": code, "level": "error", "where": where, "detail": detail}


def _resolve_job(relpath: str, job_id: str, jobs: dict[str, Any], diagnostics: list) -> dict | None:
    job = jobs.get(job_id)
    if job is None:
        diagnostics.append(
            _error("command_source_mismatch", f"{relpath}#{job_id}", f"full job {job_id!r} is absent")
        )
        return None
    return {
        "id": job_id,
        "line": job.get("line"),
        "name": job["name"],
        "if": job["if"],
        "needs": job["needs"],
        "runs_on": job["runs_on"],
        "matrix": job["matrix"],
        "env": job.get("env", {}),
        "steps": job["steps"],
    }


def full_bindings(facts: Facts) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    nodes = node_index(facts.policy)
    bindings: dict[str, Any] = {}
    diagnostics: list[dict[str, Any]] = []
    for key, binding in sorted((facts.policy.get("full_bindings") or {}).items()):
        if key not in nodes:
            diagnostics.append(
                _error("policy_node_mismatch", f"full_bindings[{key}]", f"unknown node {key!r}")
            )
            continue
        relpath = f"{key}/{binding['workflow']}"
        jobs = facts.workflow_jobs.get(relpath)
        if jobs is None:
            diagnostics.append(
                _error(
                    "command_source_mismatch",
                    relpath,
                    f"full workflow {binding['workflow']} was not found",
                )
            )
            continue
        resolved = [
            job
            for job in (_resolve_job(relpath, job_id, jobs, diagnostics) for job_id in binding["jobs"])
            if job is not None
        ]
        bindings[key] = {"workflow": binding["workflow"], "jobs": resolved}
    return bindings, diagnostics