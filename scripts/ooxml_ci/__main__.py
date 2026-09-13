"""`python3 -m ooxml_ci` entry point (run from ooxml-stack/scripts or with PYTHONPATH)."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python3 scripts/ooxml_ci/__main__.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ooxml_ci.cli import main  # type: ignore
else:
    from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
