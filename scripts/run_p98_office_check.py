"""P98-B: native Office live-open check.

Opens representative generated outputs in the installed Microsoft Office apps
(Word / PowerPoint / Excel) on macOS and records whether each file opens clean
(pass), triggers a repair/recovery dialog (repair_dialog), a fatal error
(crash_error), or never completes loading (timeout).

This is a best-effort lightweight gate. A clean open here is evidence surfaced
through desktop Office, not a full native-Office compatibility claim.

Usage:
    python3 scripts/run_p98_office_check.py [--out DIR] [--file PATH ...]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release-evidence" / "p98" / "office-verification"

DEFAULT_FILES = [
    ROOT.parent / "python-docx" / "playground" / "demo.docx",
    ROOT.parent / "python-docx" / "playground" / "demo_smartart_basic.docx",
    ROOT.parent / "python-pptx" / "playground" / "demo.pptx",
    ROOT.parent / "python-xlsx" / "tests" / "fixtures" / "sample.xlsx",
]

APP_BY_EXT = {
    ".docx": "Microsoft Word", ".docm": "Microsoft Word", ".dotx": "Microsoft Word",
    ".pptx": "Microsoft PowerPoint", ".pptm": "Microsoft PowerPoint",
    ".potx": "Microsoft PowerPoint", ".ppsx": "Microsoft PowerPoint", ".ppt": "Microsoft PowerPoint",
    ".xlsx": "Microsoft Excel", ".xlsm": "Microsoft Excel",
}

COUNT_QUERY = {
    "Microsoft Word": "count of documents",
    "Microsoft PowerPoint": "count of presentations",
    "Microsoft Excel": "count of workbooks",
}


def _run(script: str, timeout: int = 20) -> str:
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True,
                           text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return ""


_PRIVILEGE = "-10004"  # macOS Automation/Accessibility consent not granted


def automation_permission_ok(app: str) -> bool:
    """Return True only if the host can read Office document state (permission granted)."""
    query = COUNT_QUERY.get(app)
    if not query:
        return False
    out = _run(f'tell application "{app}" to get {query}', timeout=10)
    return bool(out) and "privilege" not in out.lower() and "-10004" not in out


def _count(app: str) -> int:
    query = COUNT_QUERY.get(app)
    if not query:
        return 0
    out = _run(f'tell application "{app}" to get {query}', timeout=10)
    try:
        return int(out.strip())
    except ValueError:
        return 0


def _repair_status(app: str) -> str:
    """Return 'repair', 'error', or '' based on a visible Office dialog."""
    probe = (
        'tell application "System Events" to tell process "' + app + '"\n'
        '  set found to ""\n'
        '  repeat with w in windows\n'
        '    if (subrole of w) is "AXDialog" then\n'
        '      set b to name of every button of w\n'
        '      if b contains "Repair" or b contains "Recover" then\n'
        '        set found to "repair"\n'
        '      else if (count of b) is 1 then\n'
        '        set found to "error"\n'
        '      end if\n'
        '    end if\n'
        '  end repeat\n'
        '  return found\n'
        'end tell'
    )
    out = _run(probe, timeout=10)
    return out if out in {"repair", "error"} else ""


def _portable(path: Path) -> str:
    """Repo/workspace-relative path so no local user path leaks into artifacts."""
    for root in (ROOT, ROOT.parent):
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
    return path.name


def check_open(path: Path, poll_seconds: int = 90) -> dict[str, object]:
    ext = path.suffix.lower()
    app = APP_BY_EXT.get(ext)
    if app is None:
        return {"file": _portable(path), "app": None, "ext": ext,
                "status": "unsupported_extension", "loaded": False}
    # Clean slate.
    subprocess.run(["killall", "-9", app], capture_output=True, timeout=10)
    time.sleep(2)

    # If the host cannot read Office state, the live check cannot produce a
    # defined result; record the environment blocker instead of a fake pass.
    if not automation_permission_ok(app):
        _run('try\ntell application "%s" to quit\nend try' % app, timeout=8)
        return {
            "file": _portable(path), "app": app, "ext": ext,
            "status": "blocked_automation_permission", "loaded": False,
            "detail": "macOS Automation consent not granted (-10004); cannot drive Office",
        }

    _run(
        'ignoring application responses\ntell application "%s" to open POSIX file "%s"' % (app, path),
        timeout=12,
    )

    status = "timeout"
    loaded = False
    t0 = time.time()
    while (time.time() - t0) < poll_seconds:
        dlg = _repair_status(app)
        if dlg:
            status = "repair_dialog" if dlg == "repair" else "crash_error"
            break
        if _count(app) > 0:
            loaded = True
            status = "pass"
            break
        time.sleep(2)

    _run('try\ntell application "%s" to quit\nend try' % app, timeout=8)
    subprocess.run(["killall", "-9", app], capture_output=True, timeout=10)
    return {
        "file": _portable(path), "app": app, "ext": ext,
        "status": status, "loaded": loaded,
        "seconds": round(time.time() - t0, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=EVIDENCE)
    parser.add_argument("--file", action="append", type=Path, default=None,
                        help="explicit file paths to verify (repeatable)")
    args = parser.parse_args()

    files = list(args.file) if args.file else list(DEFAULT_FILES)
    results = []
    for f in files:
        if not f.exists():
            results.append({"file": _portable(f), "status": "missing", "loaded": False})
            continue
        print(f"checking {f} ...", flush=True)
        results.append(check_open(f))

    statuses = {}
    for r in results:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    doc = {
        "schema_version": "p98-office-verification-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "claim": (
            "Best-effort native Office open check of representative generated "
            "outputs on macOS. A pass here is evidence surfaced through desktop "
            "Office, not a full native-Office compatibility claim. A "
            "blocked_automation_permission result is an environment blocker, "
            "not a pass or a repair-dialog result."
        ),
        "check_count": len(results),
        "status_counts": statuses,
        "results": results,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "office-verification-results.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"check_count": len(results), "status_counts": statuses}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())