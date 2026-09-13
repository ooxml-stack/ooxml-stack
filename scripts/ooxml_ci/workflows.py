"""Workflow parsing for the inventory fields, backed by a YAML node tree.

Only what the plan promises is read: job and step bindings with source lines,
``env``, ``run``, ``if``, ``shell``, ``working-directory`` and the matrix.
Actions expressions are recorded verbatim and never evaluated. A structure the
inventory cannot read without guessing is reported as ``unsupported_workflow``
rather than silently dropped.
"""

from __future__ import annotations

from typing import Any

from . import bashwords, yamlnodes as yaml_nodes
from .yamlnodes import NodeError

UNSUPPORTED = "unsupported_workflow"


def _error(where: str, detail: str) -> dict[str, Any]:
    return {"code": UNSUPPORTED, "level": "error", "where": where, "detail": detail}


def _text(node, where: str, errors: list) -> str | None:
    """A scalar field: absent is ``None``; a non-scalar or tagged node is an error."""
    if node is None:
        return None
    value = yaml_nodes.scalar(node)
    if value is None:
        errors.append(_error(where, f"expected a plain YAML scalar, got {yaml_nodes.describe(node)}"))
    return value


def _env(node, where: str, errors: list) -> dict[str, str]:
    try:
        items = yaml_nodes.mapping(node, f"{where} env")
    except NodeError as error:
        errors.append(_error(where, str(error)))
        return {}
    out: dict[str, str] = {}
    for name, value, _ in items:
        if not yaml_nodes.is_standard_scalar(value):
            errors.append(_error(where, f"env {name!r} is not a string value; got {yaml_nodes.describe(value)}"))
            continue
        out[name] = value.value
    return out


def _structured(node, label: str, errors: list) -> Any:
    """Recursively read a structured field, reusing the node-level validation."""
    if node is None:
        return None
    try:
        return yaml_nodes.plain(node, label)
    except NodeError as error:
        errors.append(_error(f"{label} (line {yaml_nodes.line_of(node)})", str(error)))
        return None


def _matrix(strategy, where: str, errors: list) -> Any:
    try:
        items = yaml_nodes.as_dict(strategy, f"{where} strategy")
    except NodeError as error:
        errors.append(_error(where, str(error)))
        return {}
    return _structured(items.get("matrix"), f"{where} matrix", errors) or {}


def _step(raw: dict[str, Any], where: str, line: int, errors: list) -> dict[str, Any]:
    return {
        "line": line,
        "name": _text(raw.get("name"), where, errors),
        "uses": _text(raw.get("uses"), where, errors),
        "run": _text(raw.get("run"), where, errors),
        "if": _text(raw.get("if"), where, errors),
        "shell": _text(raw.get("shell"), where, errors),
        "cwd": _text(raw.get("working-directory"), where, errors),
        "env": _env(raw.get("env"), where, errors),
    }


def _read_steps(node, where: str, errors: list) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Parsed steps paired with their raw mappings, so callers can reach ``uses``/``run``."""
    try:
        items = yaml_nodes.sequence(node, f"{where} steps")
    except NodeError as error:
        errors.append(_error(where, str(error)))
        return []
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for index, step_node in enumerate(items):
        label = f"{where} step[{index}]"
        try:
            raw = yaml_nodes.as_dict(step_node, label)
        except NodeError as error:
            errors.append(_error(label, str(error)))
            continue
        out.append((_step(raw, label, yaml_nodes.line_of(step_node), errors), raw))
    return out


def _record_uses(node, where: str, uses: list, errors: list) -> None:
    raw = _text(node, where, errors)
    if not raw or "/" not in raw:
        return
    name, _, ref = raw.partition("@")
    uses.append({"uses": raw, "name": name, "ref": ref or None, "line": yaml_nodes.line_of(node)})


def _clone_refs(node, where: str, errors: list) -> list[dict[str, Any]]:
    """Clone URLs in a ``run`` body, read from the parsed scalar.

    Folding, quoting, escapes and comments are resolved by YAML and the bash
    grammar, so a single-line, literal or folded command reads the same. Actions
    expressions are masked before parsing, so a dynamic argument keeps its
    position and never swallows the static repository URL that follows it. Only
    ``run`` is scanned, and the reported line never leaves the ``run`` node:
    literal blocks keep a one-to-one line mapping, everything else reports the
    node itself.
    """
    base = yaml_nodes.line_of(node)
    literal = node.style == "|"
    shell = bashwords.commands(node.value)
    for problem in shell.problems:
        errors.append(_error(where, problem))
    if shell.unreadable:
        errors.append(_error(where, "the run body could not be read as shell without guessing"))
    out: list[dict[str, Any]] = []
    for offset, tokens in shell.commands:
        target = bashwords.clone_target(tokens)
        if target is None:
            continue
        line = base + 1 + offset if literal else base
        kind, value = target
        if kind == "url":
            out.append({"url": value, "line": line})
        else:
            errors.append(
                _error(
                    f"{where} (line {line})",
                    "git clone target is not statically known: "
                    + bashwords.restore(value, shell.expressions, shell.marker_prefix),
                )
            )
    return out


def _job(raw: dict[str, Any], where: str, line: int, steps: list, errors: list) -> dict[str, Any]:
    return {
        "line": line,
        "name": _text(raw.get("name"), where, errors),
        "if": _text(raw.get("if"), where, errors),
        "needs": _structured(raw.get("needs"), f"{where} needs", errors),
        "runs_on": _structured(raw.get("runs-on"), f"{where} runs-on", errors),
        "matrix": _matrix(raw.get("strategy"), where, errors),
        "env": _env(raw.get("env"), where, errors),
        "steps": [step for step, _ in steps],
    }


def _read_jobs(node, jobs: dict, uses: list, clones: list, errors: list) -> None:
    try:
        job_items = yaml_nodes.mapping(node, "workflow jobs")
    except NodeError as error:
        errors.append(_error("workflow jobs", str(error)))
        return
    for job_id, job_node, job_key in job_items:
        where = f"jobs.{job_id}"
        try:
            raw = yaml_nodes.as_dict(job_node, where)
        except NodeError as error:
            errors.append(_error(where, str(error)))
            continue
        steps = _read_steps(raw.get("steps"), where, errors)
        jobs[job_id] = _job(raw, where, yaml_nodes.line_of(job_key), steps, errors)
        if raw.get("uses") is not None:
            _record_uses(raw["uses"], where, uses, errors)
        for index, (_, step_raw) in enumerate(steps):
            label = f"{where} step[{index}]"
            if step_raw.get("uses") is not None:
                _record_uses(step_raw["uses"], label, uses, errors)
            if step_raw.get("run") is not None:
                clones.extend(_clone_refs(step_raw["run"], label, errors))


def parse_workflow(data: bytes) -> dict[str, Any]:
    """Everything the plan reads from one workflow, plus what it could not read."""
    empty: dict[str, Any] = {"uses": [], "clone_refs": [], "jobs": {}}
    try:
        document = yaml_nodes.compose(data)
    except NodeError as error:
        return {**empty, "errors": [_error("workflow", str(error))]}
    uses: list[dict[str, Any]] = []
    clones: list[dict[str, Any]] = []
    jobs: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    if document is not None:
        try:
            root = yaml_nodes.as_dict(document, "workflow")
        except NodeError as error:
            errors.append(_error("workflow", str(error)))
        else:
            _read_jobs(root.get("jobs"), jobs, uses, clones, errors)
    return {"uses": uses, "clone_refs": clones, "jobs": jobs, "errors": errors}


def parse_workflow_uses(data: bytes) -> list[dict[str, Any]]:
    return parse_workflow(data)["uses"]


def parse_clone_refs(data: bytes) -> list[dict[str, Any]]:
    return parse_workflow(data)["clone_refs"]


def parse_workflow_jobs(data: bytes) -> dict[str, dict[str, Any]]:
    return parse_workflow(data)["jobs"]