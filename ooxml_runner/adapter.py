"""Load and validate a repository adapter.

An adapter is the seam between the generic runner and one repository's checks.
It is named by the plan's full binding and imported from the repository snapshot
with that snapshot's root pinned to the front of ``sys.path``, so ``scripts.ci``
always resolves to the repository under test rather than to whatever else
happens to be importable.

The runner requires exactly these names and fails closed when one is missing:
``describe``, ``load_config``, ``input_hashes``, ``operations``,
``verify_report``.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

REQUIRED = ("describe", "load_config", "input_hashes", "operations", "verify_report")


class AdapterError(RuntimeError):
    """The adapter is unknown, unimportable, or does not honour the protocol."""


def load(repo_root: Path, module_name: str) -> ModuleType:
    """Import ``module_name`` from ``repo_root`` with an explicit path priority.

    The module is loaded from its file with a name unique to that checkout.
    Importing it by its dotted name would hand back whatever ``scripts.ci.adapter``
    was imported first, so a second repository would silently run the first
    repository's checks.
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


def describe(adapter: ModuleType, root: Path) -> dict[str, Any]:
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


def operations(adapter: ModuleType, root: Path, reports: Path, config: dict[str, Any]) -> dict:
    """Build the stage implementations and assert they match the declared order."""
    declared = list(adapter.describe(Path(root))["stages"])
    built = adapter.operations(Path(root), Path(reports), config)
    if list(built) != declared:
        raise AdapterError(
            "implemented stages differ from the declared stage contract: "
            f"{list(built)} != {declared}"
        )
    return built