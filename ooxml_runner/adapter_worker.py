"""Evaluate one repository snapshot's adapter inside that snapshot.

The runner is usually started from a repository's own CI entry point, so the
calling process has already imported *its* ``scripts.ci`` package. Importing the
adapter out of a snapshot in that process would hand the adapter the caller's
modules: ``from scripts.ci import spec`` resolves through the already-loaded
parent package, not through the snapshot that was just put on ``sys.path``.

This worker is that snapshot's own interpreter. It is started with ``-I``, so
neither the caller's ``PYTHONPATH``, its user site directory nor its working
directory shape the import; the snapshot root is prepended explicitly and the
adapter is loaded from a file inside it.

Protocol: one JSON request on stdin, one JSON answer on stdout, exit 0 when the
operation returned and non-zero when it raised. It expresses only the operations
the adapter protocol already declares - it runs no checks of its own.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

OPERATIONS = ("describe", "load_config", "input_hashes", "verify_report", "is_dirty")
REQUIRED = ("describe", "load_config", "input_hashes", "operations", "verify_report")


def load(snapshot: Path, module_name: str):
    """Import ``module_name`` from ``snapshot`` under a name unique to it."""
    snapshot = Path(snapshot).resolve()
    source = snapshot / (module_name.replace(".", "/") + ".py")
    if not source.is_file():
        raise ImportError(f"adapter module {module_name!r} not found under {snapshot}")
    unique = "ooxml_adapter_{}_{}".format(
        hashlib.sha256(str(snapshot).encode("utf-8")).hexdigest()[:12], module_name.replace(".", "_")
    )
    spec = importlib.util.spec_from_file_location(unique, source)
    if spec is None or spec.loader is None:
        raise ImportError(f"adapter {module_name!r} is not importable from {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(unique, None)
        raise ImportError(
            f"adapter {module_name!r} failed to import: {type(exc).__name__}: {exc}"
        ) from exc
    missing = [name for name in REQUIRED if not callable(getattr(module, name, None))]
    if missing:
        raise ImportError(f"adapter {module_name!r} is missing: {', '.join(missing)}")
    return module


def invoke(module, operation: str, request: dict):
    """Call one declared adapter operation and return its JSON-able result."""
    if operation == "verify_report":
        module.verify_report(request["report"], request["commit"], request["config"], request["inputs"])
        return None
    return getattr(module, operation)(Path(request["root"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ooxml_runner.adapter_worker")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--operation", required=True, choices=OPERATIONS)
    args = parser.parse_args(argv)
    try:
        request = json.loads(sys.stdin.read() or "{}")
        request.setdefault("root", args.snapshot)
        value = invoke(load(args.snapshot, args.module), args.operation, request)
    except BaseException as exc:  # noqa: BLE001 - the caller needs the reason, not a traceback
        json.dump({"ok": False, "type": type(exc).__name__, "error": f"{type(exc).__name__}: {exc}"},
                  sys.stdout)
        return 1
    json.dump({"ok": True, "value": value}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())