"""The ``--write`` / ``--check`` entry point and its verdict rendering.

Only the standard library, the dependency precheck and the workspace layout are
imported at module level. The parsing layer pulls in ``packaging`` and ``yaml``,
so it is imported *after* the gate has passed: a missing package must produce a
preparation command, not an ``ImportError`` traceback.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from . import deps
from .paths import HOST_KEY, PLAN_RELPATH, SCAN_RELPATH, InputError, find_root


def _canonical_json(payload: Any) -> str:
    """Canonical serialization lives in the read layer; import it post-gate."""
    from .inputs import canonical_json

    return canonical_json(payload)


def structural_verdict(plan: dict[str, Any], strict: bool) -> list[str]:
    problems = []
    for item in plan["diagnostics"]:
        if item["level"] == "error" or (strict and item["level"] == "warning"):
            problems.append(f"{item['level']}:{item['code']} {item['where']} — {item['detail']}")
    return problems


def scan_verdict(scan_report: dict[str, Any], strict: bool) -> list[str]:
    problems = []
    for item in scan_report["diagnostics"]:
        level = item["level"]
        blocking = (
            level == "error"
            or (level == "unverifiable" and item.get("required"))
            or (strict and level in ("warning", "unverifiable"))
        )
        if blocking:
            problems.append(f"{level}:{item['code']} {item['where']} — {item['detail']}")
    return problems


def required_unverifiable(scan_report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in scan_report["diagnostics"]
        if item["level"] == "unverifiable" and item.get("required")
    ]


def _load(root: pathlib.Path):
    from . import inputs as read_layer

    policy = read_layer.load_policy(root)
    files, missing = read_layer.select_inputs(root, policy)
    facts = read_layer.gather_facts(root, policy, files, missing)
    return policy, facts


def _base_verdict(mode: str, root: pathlib.Path, plan: dict, scan_report: dict) -> dict[str, Any]:
    return {
        "mode": mode,
        "root": str(root),
        "plan": f"{HOST_KEY}/{PLAN_RELPATH}",
        "scan": f"{HOST_KEY}/{SCAN_RELPATH}",
        "inputs_digest": plan["inputs_digest"],
        "counts": plan["diagnostic_counts"],
        "scan_counts": scan_report["diagnostic_counts"],
    }


def _run_write(root: pathlib.Path, plan: dict, scan_report: dict, as_json: bool) -> int:
    plan_path = root / HOST_KEY / PLAN_RELPATH
    scan_path = root / HOST_KEY / SCAN_RELPATH
    verdict = _base_verdict("write", root, plan, scan_report)
    blocked = required_unverifiable(scan_report)
    scan_path.parent.mkdir(parents=True, exist_ok=True)
    if blocked:
        scan_path.write_text(_canonical_json(scan_report), encoding="utf-8")
        verdict["result"] = "failed"
        verdict["reason"] = "required facts unverifiable; existing plan left untouched"
        verdict["problems"] = [f"{item['code']} {item['where']} — {item['detail']}" for item in blocked]
        _report(verdict, as_json)
        return 1
    plan_bytes = _canonical_json(plan)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(plan_bytes, encoding="utf-8")
    scan_path.write_text(_canonical_json(scan_report), encoding="utf-8")
    verdict["result"] = "written"
    verdict["plan_bytes"] = len(plan_bytes)
    _report(verdict, as_json)
    return 0


def _persist_scan(scan_path: pathlib.Path, scan_report: dict, verdict: dict[str, Any]) -> None:
    """The scan is a time-point observation: every check refreshes it, pass or fail."""
    payload = dict(scan_report)
    payload["check"] = {
        "result": verdict["result"],
        "byte_identical": verdict.get("byte_identical"),
        "problems": verdict["problems"],
    }
    scan_path.parent.mkdir(parents=True, exist_ok=True)
    scan_path.write_text(_canonical_json(payload), encoding="utf-8")


def _run_check(
    root: pathlib.Path, plan: dict, scan_report: dict, strict: bool, as_json: bool
) -> int:
    plan_path = root / HOST_KEY / PLAN_RELPATH
    scan_path = root / HOST_KEY / SCAN_RELPATH
    verdict = _base_verdict("check", root, plan, scan_report)
    problems: list[str] = []
    committed = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else None
    if committed is None:
        problems.append("plan is missing; run --write")
        byte_identical = False
    else:
        byte_identical = committed == _canonical_json(plan)
        if not byte_identical:
            problems.append("regenerated plan differs from the committed plan (byte comparison)")
    problems.extend(structural_verdict(plan, strict))
    problems.extend(scan_verdict(scan_report, strict))
    verdict["byte_identical"] = byte_identical
    verdict["problems"] = problems
    verdict["result"] = "ok" if not problems else "failed"
    _persist_scan(scan_path, scan_report, verdict)
    _report(verdict, as_json)
    return 0 if not problems else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ooxml_ci", description="Ecosystem inventory for the ooxml repos")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenerate the plan (and scan)")
    mode.add_argument("--check", action="store_true", help="verify the plan and the scan")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--offline", action="store_true", help="skip remote probes")
    parser.add_argument("--root", default=None, help="workspace root (default: discover)")
    parser.add_argument("--json", action="store_true", help="print machine-readable verdict")
    return parser


def _dependency_gate(root: pathlib.Path) -> int | None:
    """Refuse to read or write anything when the pinned environment is wrong.

    A different ``packaging`` release can change a version verdict, so the tool
    never runs against an unverified interpreter and never installs anything.
    """
    report = deps.check(root)
    if not report["problems"]:
        return None
    print("dependency error: the pinned inventory environment is not active", file=sys.stderr)
    for problem in report["problems"]:
        print(f"  - {problem}", file=sys.stderr)
    print("prepare it with:", file=sys.stderr)
    print(f"  {deps.prepare_command()}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    start = pathlib.Path(args.root).resolve() if args.root else pathlib.Path.cwd().resolve()
    try:
        root = find_root(start)
    except InputError as error:
        print(f"input error: {error}", file=sys.stderr)
        return 2
    blocked = _dependency_gate(root)
    if blocked is not None:
        return blocked
    from .plan import build_plan
    from .scan import scan

    try:
        policy, facts = _load(root)
    except InputError as error:
        print(f"input error: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # malformed input must not silently write a plan
        print(f"input error: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    plan = build_plan(facts)
    scan_report = scan(root, policy, plan, offline=args.offline)
    if args.write:
        return _run_write(root, plan, scan_report, args.json)
    return _run_check(root, plan, scan_report, args.strict, args.json)


def _report(verdict: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"mode          : {verdict['mode']}")
    print(f"root          : {verdict['root']}")
    print(f"inputs digest : {verdict['inputs_digest']}")
    print(f"plan counts   : {verdict['counts']}")
    print(f"scan counts   : {verdict['scan_counts']}")
    if "byte_identical" in verdict:
        print(f"plan bytes    : {'identical' if verdict['byte_identical'] else 'DIFFERENT'}")
    print(f"result        : {verdict['result']}")
    for problem in verdict.get("problems", [])[:40]:
        print(f"  - {problem}")
    if verdict.get("reason"):
        print(f"  reason: {verdict['reason']}")