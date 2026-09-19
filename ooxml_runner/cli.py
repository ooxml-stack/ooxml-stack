"""``describe`` / ``run`` / ``verify-report``.

``describe`` is a dry run: it resolves the commit, the runner version, the plan
identity and the adapter's static contract, and it starts nothing. It is
evidence that the request is well formed, never evidence that the gate passes.

``run`` prepares a clean snapshot of the requested commit, launches the pinned
container, streams the log, and verifies the resulting report against the
request before returning success.

``verify-report`` re-derives the expected values from the caller's arguments and
the repository at the requested commit, then checks the report against them. It
never trusts the report's own account of which commit, runner or plan produced
it.

The three public functions below are the programmatic surface; the argparse
wrappers exist so the same code is reachable from a shell.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from . import adapter as adapters
from . import container as container_module
from . import docker as docker_module
from . import identity as identity_module
from . import plan as plan_module
from . import report as report_module
from . import signals as signals_module
from . import snapshot as snapshot_module

_COMMANDS = ("describe", "run", "verify-report")

def _resolve(*, root, repo: str, commit: str, runner_commit: str, plan, repo_path=None) -> dict[str, Any]:
    """Resolve and validate everything the request names, without executing.

    ``repo_path`` overrides the default ``root/repo`` layout so a linked worktree
    or any other checkout location can be verified without renaming it.

    The runner identity kept here is the one derived from the pinned commit, not
    the one the working tree happens to hash to, so a dirty checkout cannot
    define its own expectation.
    """
    root = Path(root).resolve()
    repo_path = Path(repo_path).resolve() if repo_path else root / repo
    if not repo_path.is_dir():
        raise SystemExit(f"repository not found: {repo_path}")
    resolved = snapshot_module.resolve_commit(repo_path, commit)
    trusted = identity_module.require_expected(identity_module.identity(), runner_commit)
    loaded = plan_module.load(Path(plan).resolve())
    return {
        "root": root, "repo_path": repo_path, "repo": repo, "commit": resolved,
        "runner": trusted, "plan": loaded, "binding": plan_module.binding_for(loaded, repo),
    }


def _view(request: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """The snapshot's own adapter, evaluated in that snapshot's interpreter."""
    adapter = adapters.SnapshotAdapter(
        repo_root, request["binding"]["adapter"], Path(request["runner"]["root"])
    )
    return {
        "adapter": adapter,
        "described": adapters.describe(adapter, repo_root),
        "config": adapter.load_config(repo_root),
    }


def _expected(request: dict[str, Any], stages: list[str]) -> dict[str, Any]:
    return {
        "repository": request["repo"], "commit": request["commit"],
        "runner_commit": request["runner"]["commit"],
        "runner_source_sha256": request["runner"]["source_sha256"],
        "plan_sha256": request["plan"]["sha256"],
        "inputs_digest": request["plan"]["inputs_digest"],
        "inputs_reverified": plan_module.reverify_inputs(
            request["plan"], request["root"], request["repo"], request["commit"]
        ),
        "binding": request["binding"],
        "stages": stages,
    }


def _with_snapshot(request: dict[str, Any], prefix: str, action):
    with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
        snapshot = snapshot_module.checkout(
            request["repo_path"], request["commit"], Path(temporary) / request["repo"]
        )
        return action(snapshot, _view(request, snapshot))


def describe_repository(*, root, repo, commit="HEAD", runner_commit, plan) -> dict[str, Any]:
    """Validate the request and return the static execution contract."""
    request = _resolve(root=root, repo=repo, commit=commit, runner_commit=runner_commit, plan=plan)

    def build(snapshot, view):
        return {
            "repository": request["repo"],
            "commit": request["commit"],
            "runner": {"commit": request["runner"]["commit"],
                       "source_sha256": request["runner"]["source_sha256"]},
            "plan": {"path": request["plan"]["path"], "sha256": request["plan"]["sha256"],
                     "inputs_digest": request["plan"]["inputs_digest"],
                     "inputs_reverified": plan_module.reverify_inputs(
                         request["plan"], request["root"], request["repo"], request["commit"])},
            "binding": request["binding"],
            "stages": list(view["described"]["stages"]),
            "environment": view["described"].get("environment", {}),
            "implementation": view["described"].get("implementation"),
            "static_commands": view["described"].get("static_commands", []),
            "runtime_steps": view["described"].get("runtime_steps", []),
            "executes": False,
        }

    return _with_snapshot(request, "ooxml-describe-", build)


def verify_report_file(*, root, repo, commit, runner_commit, plan, report) -> dict[str, Any]:
    """Verify an existing report against the request, not against its own claims."""
    request = _resolve(root=root, repo=repo, commit=commit, runner_commit=runner_commit, plan=plan)
    payload = report_module.load(Path(report))

    def check(snapshot, view):
        expected = _expected(request, list(view["described"]["stages"]))
        report_module.verify_generic(payload, expected)
        # The inputs are re-derived from the requested commit. Passing the
        # report's own ``inputs`` back in would compare it against itself and
        # accept any digest the report happened to declare.
        inputs = view["adapter"].input_hashes(snapshot)
        view["adapter"].verify_report(payload, request["commit"], view["config"], inputs)
        return {"repository": request["repo"], "commit": request["commit"],
                "report": str(report), "result": "pass"}

    return _with_snapshot(request, "ooxml-verify-", check)


def _cached_pass(directory: Path, expected: dict, adapter, config: dict, inputs: dict) -> Path | None:
    """Reuse a prior pass only when it matches commit, runner, plan AND inputs."""
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*/report.json")):
        try:
            candidate = report_module.load(path)
            report_module.verify_generic(candidate, expected)
            adapter.verify_report(candidate, expected["commit"], config, inputs)
        except (report_module.ReportError, adapters.AdapterError, OSError,
                ValueError, TypeError, KeyError):
            continue
        return path.parent
    return None


def _launch(request: dict[str, Any], workspace, reports, config, timeout) -> dict:
    name = "ooxml-runner-" + uuid.uuid4().hex
    argv = docker_module.command(
        workspace=workspace, reports=reports, runner_root=Path(request["runner"]["root"]),
        plan=Path(request["plan"]["path"]), config=config, commit=request["commit"],
        runner_commit=request["runner"]["commit"], name=name,
        cpus=docker_module.cpu_limit(), repository=request["repo"], adapter=request["binding"]["adapter"],
    )
    print(f"Checking {request['commit']}; reports: {reports}", flush=True)
    result = docker_module.execute(argv, reports, snapshot_module.credential(), timeout, name)
    if result:
        raise container_module.ContainerError(f"CI failed with exit {result}; reports: {reports}", result)
    return report_module.load(reports)


def run_repository(
    *, root, repo, commit="HEAD", runner_commit, plan, output, reuse_success=False, timeout=None,
    repo_path=None,
) -> dict[str, Any]:
    """Run the full verification for one commit and return the verified report."""
    request = _resolve(root=root, repo=repo, commit=commit, runner_commit=runner_commit,
                       plan=plan, repo_path=repo_path)
    inputs_reverified = plan_module.reverify_inputs(
        request["plan"], request["root"], request["repo"], request["commit"])
    output_root = Path(output).resolve()

    def execute(snapshot, view):
        config, adapter = view["config"], view["adapter"]
        inputs = adapter.input_hashes(snapshot)
        expected = _expected(request, list(view["described"]["stages"]))
        if reuse_success:
            cached = _cached_pass(output_root / request["commit"], expected, adapter, config, inputs)
            if cached is not None:
                print(f"PASS {request['commit']}; reusing report: {cached / 'report.json'}", flush=True)
                return {"repository": request["repo"], "commit": request["commit"], "result": "pass",
                        "report": str(cached / "report.json"), "reused": True}
        reports = output_root / request["commit"] / ("ooxml-run-" + uuid.uuid4().hex)
        reports.mkdir(parents=True)
        skeleton = report_module.new_report(
            repository=request["repo"], commit=request["commit"], runner=request["runner"],
            plan={"path": request["plan"]["path"], "sha256": request["plan"]["sha256"],
                  "inputs_digest": request["plan"]["inputs_digest"],
                  "inputs_reverified": inputs_reverified},
            binding=request["binding"], image=config["image"], inputs=inputs,
            stages=expected["stages"],
        )
        report_module.save(reports, skeleton)
        try:
            result = _launch(request, snapshot.parent, reports, config,
                             timeout or float(config["timeout_seconds"]))
            report_module.verify_generic(result, expected)
            adapter.verify_report(result, request["commit"], config, inputs)
        except BaseException as exc:
            container_module.finalize_host_failure(reports, skeleton, exc)
            raise
        print(f"PASS {request['commit']}; report: {reports / 'report.json'}", flush=True)
        return {"repository": request["repo"], "commit": request["commit"],
                "report": str(reports / "report.json"), "result": "pass",
                "stages": len(result["stages"])}

    with signals_module.termination_as_interrupt():
        return _with_snapshot(request, "ooxml-run-", execute)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ooxml_runner", description="Shared ecosystem verification runner")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in _COMMANDS:
        child = sub.add_parser(name, help=f"{name} the full verification for one repository commit")
        child.add_argument("--root", required=True, help="workspace root containing the repositories")
        child.add_argument("--repo", required=True, help="repository key, e.g. ooxml-operation-engine")
        child.add_argument("--commit", required=True, help="full commit id to verify")
        child.add_argument("--runner-commit", required=True, help="full commit id of the runner itself")
        child.add_argument("--plan", required=True, help="path to the ecosystem plan file")
        child.add_argument("--json", action="store_true", help="print a machine-readable result")
        if name == "run":
            child.add_argument("--output", required=True, help="root directory for run reports")
            child.add_argument("--reuse-success", action="store_true", help="reuse a matching cached pass")
            child.add_argument("--timeout", type=float, default=None, help="override the wall-clock timeout")
        if name == "verify-report":
            child.add_argument("--report", required=True, help="report.json to verify")
    return parser


def _emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    for key in ("repository", "commit", "result", "reused", "report"):
        if key in payload:
            print(f"{key:12}: {payload[key]}")
    if "runner" in payload:
        print(f"{'runner':12}: {payload['runner']['commit']}")
        print(f"{'plan':12}: {payload['plan']['sha256']}")
        print(f"{'stages':12}: {', '.join(payload['stages'])}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    shared = {"root": args.root, "repo": args.repo, "commit": args.commit,
              "runner_commit": args.runner_commit, "plan": args.plan}
    try:
        if args.command == "describe":
            payload = describe_repository(**shared)
        elif args.command == "verify-report":
            payload = verify_report_file(**shared, report=args.report)
        else:
            payload = run_repository(**shared, output=args.output,
                                     reuse_success=args.reuse_success, timeout=args.timeout)
    except signals_module.TerminationRequested as exc:
        # The report and the container were already finalized on the way out.
        print(f"{args.command} stopped: {exc}", file=sys.stderr)
        return 1
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as exc:  # noqa: BLE001 - every failure must be a nonzero exit, not a traceback
        print(f"{args.command} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    _emit(payload, args.json)
    return 0