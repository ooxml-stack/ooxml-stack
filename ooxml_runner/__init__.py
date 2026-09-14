"""Shared execution runner for the OOXML ecosystem full-verification gates.

The runner owns everything that is not engine-specific:

* validating an execution request against the ecosystem plan,
* preparing a clean snapshot of the requested commit,
* launching the pinned execution environment,
* timeouts, interruption, live logs and secret scrubbing,
* the execution report, its persistence and its verification.

A repository keeps ownership of its own stages, checks, parameters and report
contracts behind an *adapter* module. The runner never executes shell text that
it read out of the plan; the plan is used to verify the binding, and the adapter
supplies the implementation.

This package is deliberately a top-level package rather than ``scripts.*``.
Every repository in the ecosystem has a ``scripts`` directory and none of them
declares ``scripts/__init__.py``, so ``scripts`` currently resolves as a PEP 420
namespace package spanning whatever happens to be on ``sys.path``. Importing the
runner through that namespace would make the loaded implementation depend on
path ordering and on no repository ever adding ``scripts/__init__.py``.
A unique top-level name removes that coupling.
"""

from __future__ import annotations

SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 1
PROGRESS_SCHEMA_VERSION = 1