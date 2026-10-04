"""Bind a historical locked profile to external evidence without changing its locks."""

import argparse
import json
from pathlib import Path

from artifact_paths import artifact_dir


def bind_path(value, base):
    for prefix in ("../release-evidence/", "release-evidence/"):
        if value.startswith(prefix):
            return str(artifact_dir() / value.removeprefix(prefix))
    path = Path(value)
    return str(path if path.is_absolute() else (base / path).resolve())


def bind_profile(value, base):
    profile = json.loads(json.dumps(value))
    manifest = profile.get("evidence_manifest")
    if isinstance(manifest, str):
        profile["evidence_manifest"] = bind_path(manifest, base)
    elif isinstance(manifest, dict) and "path" in manifest:
        manifest["path"] = bind_path(manifest["path"], base)
    for item in [*profile.get("env", {}).values(), *profile.get("metric_sources", [])]:
        if isinstance(item, dict) and "path" in item:
            item["path"] = bind_path(item["path"], base)
    for name, path in profile.get("evidence", {}).items():
        if isinstance(path, str) and path.startswith("release-evidence/"):
            profile["evidence"][name] = bind_path(path, base)
    return profile


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if any((p / ".git").exists() for p in (output, *output.parents)):
        parser.error("Materialized profiles must be stored outside Git checkouts")
    source = args.profile.resolve()
    profile = bind_profile(json.loads(source.read_text()), source.parent)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, indent=2) + "\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
