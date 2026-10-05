"""Install shared agent instructions from the canonical ooxml-stack checkout."""

import argparse
import sys
from pathlib import Path

SOURCE = Path("ooxml-stack/docs/WORKSPACE-AGENTS.md")


def install(workspace):
    if not str(workspace).strip():
        raise ValueError("workspace must be explicit and nonempty")
    root = Path(workspace).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("workspace must be a directory")
    source = root / SOURCE
    if not source.is_file() or source.resolve() != source:
        raise ValueError("canonical ooxml-stack workspace instructions must be a real file")
    target = root / "AGENTS.md"
    if target.is_symlink() and target.readlink() == SOURCE:
        return target
    if target.exists() or target.is_symlink():
        raise ValueError("AGENTS.md already exists; review and preserve it before installation")
    target.symlink_to(SOURCE)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args(argv)
    try:
        print(install(args.workspace))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"workspace initialization refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
