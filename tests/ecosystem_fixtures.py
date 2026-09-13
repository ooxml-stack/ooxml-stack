"""Shared fixtures and helpers for the ecosystem inventory tests.

The suite is split by concern (plan / scan / CLI / versions) so each file stays
small; everything they share lives here.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The fixtures must declare the same pinned tool environment the real workspace
# does, otherwise the dependency gate refuses to run them.
REQUIREMENTS_TEXT = (REPO_ROOT / "ci/ecosystem-inventory-requirements.txt").read_text(encoding="utf-8")

from scripts.ooxml_ci import inputs, plan as plan_mod  # noqa: E402
from ecosystem_workflows import WORKFLOW_DOCX, WORKFLOW_FULL  # noqa: E402

CORE_SHA = "a" * 40
DOCX_SHA = "b" * 40
FRAMEWORK_SHA = "c" * 40
CORPUS_SHA = "d" * 40
PINNED_SHA = "e" * 40

PY_NODE = {"inputs": ["pyproject.toml", "uv.lock"]}


def node(key, role, layer, **extra):
    base = {
        "key": key,
        "role": role,
        "layer": layer,
        "cadence": "per-commit",
        "visibility": "private",
        "release_participation": role == "release",
        **PY_NODE,
    }
    base.update(extra)
    return base


NODES = [
    node("ooxml-stack", "meta", "release", inputs=[], visibility="public", release_participation=False),
    node("ooxml-core", "release", "core"),
    node("python-docx", "release", "app", visibility="public"),
    node("python-pptx", "release", "app", visibility="public"),
    node("ooxml-test-framework", "release", "test"),
    node("ooxml-native-corpus", "data", "corpus", inputs=[], cadence="release-only", release_participation=False),
]


def make_policy(**overrides):
    base = {
        "schema_version": 1,
        "nodes": NODES,
        "full_bindings": {
            "ooxml-core": {"workflow": ".github/workflows/full.yml", "jobs": ["full"]}
        },
        "edge_sources": [
            {
                "kind": "ci",
                "from": "environment_json",
                "file": "ooxml-core/ci/environment.json",
                "field": "repositories",
                "purpose": "engine_ci_snapshot",
            },
            {
                "kind": "data",
                "from": "environment_json",
                "file": "ooxml-core/ci/environment.json",
                "field": "corpus.release_tag",
                "pinned_commit_field": "repositories.ooxml-native-corpus",
                "purpose": "native_corpus_snapshot",
            },
        ],
        "require_uniform": [
            {"upstream": "ooxml-core", "role": "runtime", "reason": "runtime pins move together"}
        ],
        "exceptions": [],
        "workflows": {"scan_global_uses": True, "uses_owner": "ooxml-stack"},
        "scan": {"ref_timeout_seconds": 5, "allow_fetch_sha": False},
    }
    base.update(overrides)
    return base


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _docx_pyproject(core_ref="v0.6.0", framework_ref="v0.5.37"):
    return "\n".join(
        [
            "[project]",
            'name = "python-docx"',
            'version = "1.2.0"',
            f'dependencies = ["ooxml-core @ git+https://github.com/ooxml-stack/ooxml-core.git@{core_ref}"]',
            "",
            "[dependency-groups]",
            f'dev = ["ooxml-test-framework @ git+https://github.com/ooxml-stack/ooxml-test-framework.git@{framework_ref}"]',
            "",
        ]
    )


def _docx_lock(core_sha=CORE_SHA, framework_sha=FRAMEWORK_SHA, core_ref="v0.6.0"):
    return "\n".join(
        [
            "[[package]]",
            'name = "ooxml-core"',
            'version = "0.6.0"',
            f'source = {{ git = "https://github.com/ooxml-stack/ooxml-core.git?tag={core_ref}#{core_sha}" }}',
            "",
            "[[package]]",
            'name = "ooxml-test-framework"',
            'version = "0.5.37"',
            f'source = {{ git = "https://github.com/ooxml-stack/ooxml-test-framework.git?tag=v0.5.37#{framework_sha}" }}',
            "",
        ]
    )


def _pptx_lock(core_sha=CORE_SHA):
    return (
        "[[package]]\n"
        'name = "ooxml-core"\n'
        'version = "0.6.1"\n'
        f'source = {{ git = "https://github.com/ooxml-stack/ooxml-core.git?tag=v0.6.1#{core_sha}" }}\n'
    )


def build_workspace(tmp_path: pathlib.Path, policy: dict | None = None) -> pathlib.Path:
    root = tmp_path
    write(root / "ooxml-stack/ci/ecosystem-policy.json", json.dumps(policy or make_policy(), indent=2))
    write(root / "ooxml-stack/ci/ecosystem-inventory-requirements.txt", REQUIREMENTS_TEXT)
    write(root / "ooxml-core/pyproject.toml", '[project]\nname = "ooxml-core"\nversion = "0.6.0"\n')
    write(root / "ooxml-core/uv.lock", "")
    write(root / "ooxml-core/.github/workflows/full.yml", WORKFLOW_FULL)
    write(
        root / "ooxml-core/ci/environment.json",
        json.dumps(
            {
                "repositories": {"python-docx": DOCX_SHA, "ooxml-native-corpus": CORPUS_SHA},
                "corpus": {"release_tag": "native-corpus-2026-08-15.1"},
            }
        ),
    )
    write(root / "python-docx/pyproject.toml", _docx_pyproject())
    write(root / "python-docx/uv.lock", _docx_lock())
    write(root / "python-docx/.github/workflows/ci.yml", WORKFLOW_DOCX)
    write(
        root / "python-pptx/pyproject.toml",
        '[project]\nname = "python-pptx"\nversion = "1.0.2"\n'
        'dependencies = ["ooxml-core @ git+https://github.com/ooxml-stack/ooxml-core.git@v0.6.1"]\n',
    )
    write(
        root / "python-pptx/uv.lock",
        "[[package]]\n"
        'name = "ooxml-core"\n'
        'version = "0.6.1"\n'
        f'source = {{ git = "https://github.com/ooxml-stack/ooxml-core.git?tag=v0.6.1#{CORE_SHA}" }}\n',
    )
    write(
        root / "ooxml-test-framework/pyproject.toml",
        '[project]\nname = "ooxml-test-framework"\nversion = "0.5.37"\n',
    )
    write(root / "ooxml-test-framework/uv.lock", "")
    return root


def build(root: pathlib.Path) -> dict:
    policy = inputs.load_policy(root)
    files, missing = inputs.select_inputs(root, policy)
    return plan_mod.build_plan(inputs.gather_facts(root, policy, files, missing))


def git(args: list[str], cwd: pathlib.Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(cwd),
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        },
    )


def init_repo(path: pathlib.Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    git(["init", "-q", "-b", "main"], path)
    git(["remote", "add", "origin", f"https://github.com/ooxml-stack/{path.name}.git"], path)
    (path / "README.md").write_text("x\n", encoding="utf-8")
    git(["add", "."], path)
    git(["commit", "-qm", "init"], path)


SEALED_REPOS = (
    "ooxml-stack",
    "ooxml-core",
    "python-docx",
    "python-pptx",
    "ooxml-test-framework",
    "ooxml-native-corpus",
)


def head_sha(path: pathlib.Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(path), capture_output=True, text=True
    ).stdout.strip()


def seal(root: pathlib.Path) -> dict[str, str]:
    """Give every node a real checkout and repin the recorded SHAs to real commits.

    A full SHA is a required fact, so a fixture that expects a successful
    ``--write`` must make those commits locally resolvable.
    """
    heads: dict[str, str] = {}
    for name in SEALED_REPOS:
        init_repo(root / name)
        heads[name] = head_sha(root / name)
    write(
        root / "ooxml-core/ci/environment.json",
        json.dumps(
            {
                "repositories": {
                    "python-docx": heads["python-docx"],
                    "ooxml-native-corpus": heads["ooxml-native-corpus"],
                },
                "corpus": {"release_tag": "native-corpus-2026-08-15.1"},
            }
        ),
    )
    write(
        root / "python-docx/uv.lock",
        _docx_lock(heads["ooxml-core"], heads["ooxml-test-framework"]),
    )
    write(root / "python-pptx/uv.lock", _pptx_lock(heads["ooxml-core"]))
    return heads


def listing_for(heads: dict[str, str]) -> dict:
    return {
        "ok": True,
        "tags": {
            "v0.6.0": heads["ooxml-core"],
            "v0.6.1": heads["ooxml-core"],
            "v0.5.37": heads["ooxml-test-framework"],
            "v1.0.0": heads["ooxml-stack"],
            "native-corpus-2026-08-15.1": heads["ooxml-native-corpus"],
        },
        "peeled": {},
        "heads": {},
    }


def resolvable_for(monkeypatch, heads: dict[str, str]) -> None:
    from scripts.ooxml_ci import gitfacts

    monkeypatch.setattr(gitfacts, "remote_refs", lambda *a, **k: listing_for(heads))


def align_pptx(root: pathlib.Path, heads: dict[str, str]) -> None:
    """Align python-pptx with python-docx so ``--strict`` has no warning to upgrade."""
    write(
        root / "python-pptx/pyproject.toml",
        '[project]\nname = "python-pptx"\nversion = "1.0.2"\n'
        'dependencies = ["ooxml-core @ git+https://github.com/ooxml-stack/ooxml-core.git@v0.6.0"]\n',
    )
    write(
        root / "python-pptx/uv.lock",
        "[[package]]\n"
        'name = "ooxml-core"\n'
        'version = "0.6.0"\n'
        f'source = {{ git = "https://github.com/ooxml-stack/ooxml-core.git?tag=v0.6.0#{heads["ooxml-core"]}" }}\n',
    )


def sealed_workspace(tmp_path: pathlib.Path, policy: dict | None = None) -> pathlib.Path:
    root = build_workspace(tmp_path, policy)
    seal(root)
    return root