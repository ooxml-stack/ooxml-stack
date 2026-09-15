"""Load and validate a repository adapter.

An adapter is the seam between the generic runner and one repository's checks.
It is named by the plan's full binding and imported from the repository snapshot
with that snapshot's root pinned to the front of ``sys.path``, so ``scripts.ci``
always resolves to the repository under test rather than to whatever else
happens to be importable.

Inside the container that is enough: the runner checkout carries no ``scripts``
package, so the snapshot is the only candidate. On the host it is not, because
the caller's own CI entry point has already imported *its* ``scripts.ci``. The
host therefore evaluates the adapter through :class:`SnapshotAdapter`, which
runs the whole import chain in that snapshot's own interpreter.

The runner requires exactly these names and fails closed when one is missing:
``describe``, ``load_config``, ``input_hashes``, ``operations``,
``verify_report``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

REQUIRED = ("describe", "load_config", "input_hashes", "operations", "verify_report")

# Started with ``-I``: no PYTHONPATH, no user site directory, no implicit cwd.
# The snapshot root goes in first so ``scripts.ci`` is the snapshot's, and the
# runner root second so the worker itself is importable.
WORKER_BOOTSTRAP = (
    "import sys;"
    "sys.path.insert(0, sys.argv[1]);"
    "sys.path.insert(0, sys.argv[2]);"
    "from ooxml_runner.adapter_worker import main;"
    "raise SystemExit(main(sys.argv[3:]))"
)
WORKER_TIMEOUT = 300.0


class AdapterError(RuntimeError):
    """The adapter is unknown, unimportable, or does not honour the protocol."""


def load(repo_root: Path, module_name: str) -> ModuleType:
    """Import ``module_name`` from ``repo_root`` with an explicit path priority.

    This is the in-container loader. It is correct there because the runner
    checkout carries no ``scripts`` package to shadow the snapshot's; the host
    uses :class:`SnapshotAdapter` instead.
    """
    repo_root = Path(repo_root).resolve()
    relative = module_name.replace(".", "/") + ".py"
    source = repo_root / relative
    if not source.is_file():
        raise AdapterError(f"adapter module {module_name!r} not found under {repo_root}")
    root = str(repo_root)
    if root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)
    unique = "ooxml_adapter_{}_{}".format(
        hashlib.sha256(root.encode("utf-8")).hexdigest()[:12], module_name.replace(".", "_")
    )
    spec = importlib.util.spec_from_file_location(unique, source)
    if spec is None or spec.loader is None:
        raise AdapterError(f"adapter {module_name!r} is not importable from {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(unique, None)
        raise AdapterError(f"adapter {module_name!r} failed to import: {type(exc).__name__}: {exc}") from exc
    missing = [name for name in REQUIRED if not callable(getattr(module, name, None))]
    if missing:
        raise AdapterError(f"adapter {module_name!r} is missing: {', '.join(missing)}")
    return module


class SnapshotAdapter:
    """One snapshot's adapter, evaluated in that snapshot's own interpreter.

    Every host-side use of an adapter - static description, input hashing and
    report verification - goes through here, so nothing the adapter imports can
    come from the calling process.
    """

    def __init__(self, snapshot: Path, module_name: str, runner_root: Path,
                 timeout: float = WORKER_TIMEOUT):
        self._snapshot = Path(snapshot).resolve()
        self._module_name = module_name
        self._runner_root = Path(runner_root).resolve()
        self._timeout = timeout

    def _call(self, operation: str, **request: Any) -> Any:
        argv = [
            sys.executable, "-I", "-c", WORKER_BOOTSTRAP, str(self._runner_root), str(self._snapshot),
            "--snapshot", str(self._snapshot), "--module", self._module_name,
            "--operation", operation,
        ]
        try:
            result = subprocess.run(
                argv, input=json.dumps(request), capture_output=True, text=True,
                cwd=str(self._snapshot), timeout=self._timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                f"adapter {self._module_name!r} did not answer within {self._timeout}s"
            ) from exc
        except OSError as exc:
            raise AdapterError(f"adapter worker for {self._module_name!r} could not start: {exc}") from exc
        return self._decode(result)

    def _decode(self, result: subprocess.CompletedProcess) -> Any:
        try:
            answer = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise AdapterError(
                f"adapter {self._module_name!r} produced no usable answer: "
                f"{detail[-1] if detail else 'no output'}"
            ) from exc
        if not isinstance(answer, dict) or not answer.get("ok"):
            raise AdapterError(f"adapter {self._module_name!r}: {answer.get('error')}")
        return answer.get("value")

    def describe(self, root: Path) -> dict:
        return self._call("describe", root=str(root))

    def load_config(self, root: Path) -> dict:
        return self._call("load_config", root=str(root))

    def input_hashes(self, root: Path) -> dict:
        return self._call("input_hashes", root=str(root))

    def is_dirty(self, root: Path) -> bool:
        return self._call("is_dirty", root=str(root))

    def verify_report(self, report: dict, commit: str, config: dict, inputs: dict) -> None:
        self._call("verify_report", report=report, commit=commit, config=config, inputs=inputs)


def describe(adapter, root: Path) -> dict[str, Any]:
    """Static self-description; must not install, fetch, or run anything."""
    described = adapter.describe(Path(root))
    if not isinstance(described, dict):
        raise AdapterError("adapter describe() must return a mapping")
    stages = described.get("stages")
    if not stages or not all(isinstance(name, str) for name in stages):
        raise AdapterError("adapter describe() must declare a non-empty stage list")
    if len(set(stages)) != len(stages):
        raise AdapterError("adapter declares duplicate stage names")
    return described


def operations(adapter, root: Path, reports: Path, config: dict[str, Any]) -> dict:
    """Build the stage implementations and assert they match the declared order."""
    declared = list(adapter.describe(Path(root))["stages"])
    built = adapter.operations(Path(root), Path(reports), config)
    if list(built) != declared:
        raise AdapterError(
            "implemented stages differ from the declared stage contract: "
            f"{list(built)} != {declared}"
        )
    return built