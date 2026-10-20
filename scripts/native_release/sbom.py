"""Generate a minimal CycloneDX SBOM for a native payload."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from packaging.utils import parse_wheel_filename
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("packaging is required to generate the native SBOM") from exc


def _wheel_components(wheelhouse: Path) -> list[dict[str, Any]]:
    components = []
    seen = set()
    for wheel in sorted(wheelhouse.glob("*.whl")):
        try:
            name, version, _build, _tags = parse_wheel_filename(wheel.name)
        except Exception:
            continue
        key = (str(name), str(version))
        if key in seen:
            continue
        seen.add(key)
        components.append(
            {
                "type": "library",
                "name": str(name),
                "version": str(version),
                "purl": f"pkg:pypi/{name}@{version}",
            }
        )
    return components


def write_sbom(path: Path, config: dict[str, Any], wheelhouse: Path) -> None:
    components = _wheel_components(wheelhouse)
    components.extend(
        [
            {
                "type": "platform",
                "name": "CPython",
                "version": config["build"]["python_version"],
                "purl": f"pkg:generic/cpython@{config['build']['python_version']}",
            },
            {
                "type": "application",
                "name": "Nuitka",
                "version": config["build"]["nuitka"],
                "purl": f"pkg:pypi/nuitka@{config['build']['nuitka']}",
            },
        ]
    )
    payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "ooxml",
                "version": config["runtime"]["client_version"],
            },
            "properties": [
                {
                    "name": "ooxml:artifact_id",
                    "value": config["runtime"]["artifact_id"],
                },
                {
                    "name": "ooxml:runtime_classification",
                    "value": config["runtime"]["classification"],
                },
                {"name": "ooxml:fully_native", "value": "false"},
            ],
        },
        "components": components,
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
