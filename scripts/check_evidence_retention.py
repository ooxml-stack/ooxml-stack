"""Reject generated evidence directories in source checkouts, including ignored files."""

import argparse
from pathlib import Path


AREAS = ("evidence", "release-evidence", "docs/evidence", ".uxe/evidence")


def placement_problems(root):
    return [area for area in AREAS
            if (root / area).exists() or (root / area).is_symlink()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    problems = placement_problems(args.root)
    for area in problems:
        print(f"Generated evidence belongs outside source checkouts: {area}")
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
