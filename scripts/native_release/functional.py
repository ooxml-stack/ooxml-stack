"""Hermetic functional acceptance using only the packaged client."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .artifact_io import extract_candidate
from .artifact_only import run_artifact_only


class FunctionalError(ValueError):
    """A packaged artifact failed functional acceptance."""


def run_functional(
    candidate: Path, config: dict[str, Any], evidence_root: Path, internal: bool
) -> dict[str, Any]:
    artifact_only = run_artifact_only(candidate, evidence_root)
    license_path = _license_path(config)
    samples = _samples()
    run_root = evidence_root / "functional" / uuid.uuid4().hex
    run_root.mkdir(parents=True)
    with tempfile.TemporaryDirectory(dir=run_root) as folder:
        payload = extract_candidate(candidate, Path(folder))
        home = Path(folder) / "home"
        install = home / ".local/ooxml"
        install.parent.mkdir(parents=True)
        shutil.copytree(payload, install, symlinks=True)
        result = _execute(install, home, license_path, samples, config, candidate)
    result["artifact_only_pass"] = artifact_only["pass"]
    result.update(
        {"candidate": str(candidate), "mode": "DEV_ONLY" if internal else "PUBLIC"}
    )
    (evidence_root / "functional-result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    if not result["pass"]:
        raise FunctionalError(
            f"functional acceptance failed: {evidence_root / 'functional-result.json'}"
        )
    return result


def _execute(
    install: Path,
    home: Path,
    license_path: Path,
    samples: dict[str, Path],
    config: dict[str, Any],
    candidate: Path,
) -> dict[str, Any]:
    env = {
        "HOME": str(home),
        "PATH": f"{install / 'bin'}:/usr/bin:/bin",
        "LANG": "en_US.UTF-8",
    }
    client = install / "bin/ooxml"
    steps = _initial_steps(client, home, license_path, env)
    documents = home / "documents"
    documents.mkdir()
    for name, source in samples.items():
        shutil.copy2(source, documents / name)
    steps.update(_document_steps(client, env, documents))
    _uninstall_restore(install, home, license_path, candidate, steps)
    return {"pass": _passed(steps, config), "steps": steps}


def _initial_steps(client, home, license_path, env):
    return {
        "version": _step([str(client), "--version"], env),
        "unlicensed_status": _step([str(client), "status"], env),
        "activate": _step(
            [str(client), "activate", "--license", str(license_path)], env
        ),
        "status": _step([str(client), "status"], env),
        "skill": _skill_step(client, home, env),
    }


def _skill_step(client, home, env):
    skill_path = home / "skills/ooxml/SKILL.md"
    result = _step([str(client), "install-skill", "--target", str(skill_path)], env)
    result["installed"] = skill_path.is_file()
    return result


def _document_steps(client, env, documents):
    return {
        "word": _apply_validate(
            client,
            env,
            documents / "word-task.docx",
            documents / "word-out.docx",
            "text.set_container",
            "paragraphs[0]",
            {"text": "Native Release Candidate"},
        ),
        "excel": _apply_validate(
            client,
            env,
            documents / "excel-task.xlsx",
            documents / "excel-out.xlsx",
            "cell.set_value",
            "sheets[0].cells[A1]",
            {"value": "Native release budget", "value_type": "string"},
        ),
        "pptx": _apply_expected_refusal(
            client, env, documents / "ppt-task.pptx", documents / "ppt-out.pptx"
        ),
        "pdf": _step([str(client), "probe", "--profile", "pdf"], env),
        "mcp_core": _step([str(client), "probe", "--profile", "core"], env),
        "mcp_workflow": _step(
            [
                str(client),
                "probe",
                "--profile",
                "workflow",
                "--sample",
                str(documents / "word-task.docx"),
            ],
            env,
        ),
    }


def _apply_validate(client, env, source, output, operation, target, params):
    apply = _step(
        [
            str(client),
            "apply",
            "--params",
            json.dumps(
                {
                    "path": str(source),
                    "output_path": str(output),
                    "operation_id": operation,
                    "target": target,
                    "params": params,
                }
            ),
        ],
        env,
    )
    validate = _step(
        [
            str(client),
            "validate",
            "--params",
            json.dumps({"path": str(output), "level": "structural"}),
        ],
        env,
    )
    return {"apply": apply, "validate": validate}


def _apply_expected_refusal(client, env, source, output):
    result = _step(
        [
            str(client),
            "apply",
            "--params",
            json.dumps(
                {
                    "path": str(source),
                    "output_path": str(output),
                    "operation_id": "text.set_container",
                    "target": "slides[0].shapes[2]",
                    "params": {"text": "Native release"},
                }
            ),
        ],
        env,
    )
    return {
        **result,
        "expected_refusal": result["exit_code"] != 0
        and "validation_blocked" in result["stderr"]
        and not output.exists(),
    }


def _uninstall_restore(install, home, license_path, candidate, steps):
    shutil.rmtree(install)
    (home / ".ooxml/license.json").unlink(missing_ok=True)
    steps["uninstalled"] = {
        "exit_code": 0 if not install.exists() else 1,
        "install_absent": not install.exists(),
        "license_absent": not (home / ".ooxml/license.json").exists(),
    }
    restored = extract_candidate(candidate, home / "restore")
    shutil.copytree(restored, install, symlinks=True)
    env = {"HOME": str(home), "PATH": f"{install / 'bin'}:/usr/bin:/bin"}
    client = install / "bin/ooxml"
    steps["restore_activate"] = _step(
        [str(client), "activate", "--license", str(license_path)], env
    )
    steps["restore_status"] = _step([str(client), "status"], env)


def _step(command, env):
    result = subprocess.run(
        command, env=env, capture_output=True, text=True, timeout=180, check=False
    )
    parsed = None
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else None
    except ValueError:
        pass
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "json": parsed,
    }


def _passed(steps, config):
    status = steps["status"]["json"] or {}
    core = steps["mcp_core"]["json"] or {}
    workflow = steps["mcp_workflow"]["json"] or {}
    pdf = steps["pdf"]["json"] or {}
    unlicensed = steps["unlicensed_status"]["json"] or {}
    return (
        steps["version"]["exit_code"] == 0
        and unlicensed.get("serving") == "inactive"
        and unlicensed.get("reason") == "license_missing"
        and steps["activate"]["exit_code"] == 0
        and status.get("serving") == "active"
        and steps["skill"]["exit_code"] == 0
        and steps["skill"].get("installed") is True
        and steps["word"]["apply"]["json"]["success"] is True
        and steps["word"]["validate"]["json"]["passed"] is True
        and steps["excel"]["apply"]["json"]["success"] is True
        and steps["excel"]["validate"]["json"]["passed"] is True
        and steps["pptx"]["expected_refusal"] is True
        and pdf.get("available") is False
        and (pdf.get("error") or {}).get("code") == "pdf_readability_unavailable"
        and core.get("tool_count") == config["e2e"]["entitled"]["mcp_core_tool_count"]
        and workflow.get("tool_count")
        == config["e2e"]["entitled"]["mcp_workflow_tool_count"]
        and steps["uninstalled"].get("install_absent") is True
        and steps["uninstalled"].get("license_absent") is True
        and steps["restore_activate"]["exit_code"] == 0
        and (steps["restore_status"]["json"] or {}).get("serving") == "active"
    )


def _license_path(config):
    value = os.environ.get(config["entitlement"]["e2e_license_env"], "")
    if not value:
        raise FunctionalError(f"{config['entitlement']['e2e_license_env']} is required")
    return Path(value).expanduser().resolve()


def _samples():
    names = {
        "word-task.docx": "OOXML_NATIVE_E2E_WORD",
        "excel-task.xlsx": "OOXML_NATIVE_E2E_EXCEL",
        "ppt-task.pptx": "OOXML_NATIVE_E2E_PPTX",
    }
    result = {}
    for name, key in names.items():
        value = os.environ.get(key, "")
        if not value:
            raise FunctionalError(f"{key} is required")
        result[name] = Path(value).expanduser().resolve()
    return result
