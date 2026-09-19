"""Refresh or check the published plan against the default-branch basis.

``make ecosystem-plan`` reads whatever the caller's workspace happens to hold.
That is the right tool for scanning a specific checkout, and the wrong one for
reproducing the published plan: a workspace sitting on a stale branch produces a
plan that describes a state no repository is publishing. This entry point builds
the basis instead of assuming it - an isolated directory, one plain clone per
policy node, each at its own default branch - and then runs the ordinary
generator against that root.

``--write`` copies the regenerated plan back over the committed one; ``--check``
compares the committed plan with the re-derived one and changes nothing.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
import tempfile

from . import paths, workspace


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.ooxml_ci.refresh",
        description="Derive the plan from each node's default branch, in an isolated workspace",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenerate and copy the plan back")
    mode.add_argument("--check", action="store_true", help="compare the committed plan with the basis")
    parser.add_argument("--owner", default=workspace.DEFAULT_OWNER, help="GitHub owner of the nodes")
    parser.add_argument("--keep", default=None, help="prepare the workspace here instead of a temp dir")
    return parser


def _generate(root: pathlib.Path, mode: str) -> int:
    """Run the ordinary generator against the prepared root."""
    from . import cli  # imported after the workspace exists; it needs the pinned deps

    return cli.main([f"--{mode}", "--root", str(root)])


def _publish(root: pathlib.Path, checkout: pathlib.Path) -> None:
    """Copy the regenerated plan over the committed one."""
    produced = root / paths.HOST_KEY / paths.PLAN_RELPATH
    if not produced.is_file():
        raise workspace.WorkspaceError(f"the generator produced no plan at {produced}")
    shutil.copyfile(produced, checkout / paths.PLAN_RELPATH)


def _stage_for_check(root: pathlib.Path, checkout: pathlib.Path) -> None:
    """Put the plan under test in the prepared root, so --check compares it.

    ``--check`` compares against the plan in the workspace it is given. Left
    alone, that is the clone's own default-branch plan, which makes a local check
    fail immediately after a local ``--write`` - the refresh has not been pushed
    yet. The question a caller is asking here is whether *their* plan matches the
    basis, so that is the plan the prepared root gets.
    """
    source = checkout / paths.PLAN_RELPATH
    if not source.is_file():
        raise workspace.WorkspaceError(f"no plan to check at {source}")
    shutil.copyfile(source, root / paths.HOST_KEY / paths.PLAN_RELPATH)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    mode = "write" if args.write else "check"
    checkout = pathlib.Path.cwd()
    policy = checkout / paths.POLICY_RELPATH
    if not policy.is_file():
        print(f"refresh failed: no policy at {policy}", file=sys.stderr)
        return 2
    temporary = None if args.keep else tempfile.mkdtemp(prefix="ooxml-ecosystem-basis-")
    root = pathlib.Path(args.keep or temporary)
    try:
        cloned = workspace.prepare(root, policy, args.owner)
        print(f"basis: {len(cloned)} nodes cloned at their default branches under {root}", flush=True)
        if mode == "check":
            _stage_for_check(root, checkout)
        code = _generate(root, mode)
        if code == 0 and mode == "write":
            _publish(root, checkout)
            print(f"wrote {paths.PLAN_RELPATH} from the default-branch basis", flush=True)
        return code
    except workspace.WorkspaceError as exc:
        print(f"refresh failed: {exc}", file=sys.stderr)
        return 2
    finally:
        if temporary:
            shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())