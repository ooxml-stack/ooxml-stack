import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_evidence_retention import main, placement_problems
from materialize_release_profile import bind_profile


@pytest.mark.parametrize("area", ["evidence", "release-evidence"])
def test_gate_rejects_all_artifact_types_including_ignored(tmp_path, area):
    assert main(["--root", str(tmp_path)]) == 0
    (tmp_path / ".gitignore").write_text(area + "/\n")
    target = tmp_path / area
    target.mkdir()
    (target / "result.json").write_text("{}")
    assert main(["--root", str(tmp_path)]) == 1
    (target / "result.json").unlink()
    target.rmdir()
    target.symlink_to(tmp_path / "missing", target_is_directory=True)
    assert placement_problems(tmp_path) == [area]


def test_profile_binding_preserves_locks_and_nested_relative_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("OOXML_ARTIFACT_ROOT", str(tmp_path / "store"))
    original = {"evidence_manifest": "../release-evidence/p98/manifest.json",
                "env": {"CORPUS": {"path": "../../corpus", "required_files": [
                    {"path": "manifests/corpus.csv", "sha256": "sealed", "size_bytes": 8}]}},
                "metric_sources": [{"path": "../release-evidence/p98/summary.json"}],
                "expected_metrics": {"gate_pass": False}}
    frozen = json.dumps(original)
    result = bind_profile(original, tmp_path / "repo/release-profiles")
    assert result["evidence_manifest"] == str(tmp_path / "store/ooxml-stack/release-evidence/p98/manifest.json")
    assert result["env"]["CORPUS"]["path"] == str(tmp_path / "corpus")
    assert result["env"]["CORPUS"]["required_files"] == original["env"]["CORPUS"]["required_files"]
    assert result["expected_metrics"] == original["expected_metrics"]
    assert json.dumps(original) == frozen
