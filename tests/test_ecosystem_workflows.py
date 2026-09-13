"""Workflow-parsing acceptance tests: YAML semantics and the fields the plan reads."""

from __future__ import annotations

from ecosystem_fixtures import build_workspace
from ecosystem_workflows import (
    WORKFLOW_BROKEN_YAML,
    WORKFLOW_ENV_EDGE_CASES,
    WORKFLOW_ENV_NESTED,
    WORKFLOW_FULL_ENV,
)
from scripts.ooxml_ci import workflows


def test_parse_workflow_uses_records_line_and_ref(tmp_path):
    root = build_workspace(tmp_path)
    entries = workflows.parse_workflow_uses((root / "python-docx/.github/workflows/ci.yml").read_bytes())
    assert entries[0]["ref"] == "v1.0.0"
    assert entries[0]["line"] == 6


def test_parse_clone_refs_finds_repository_urls(tmp_path):
    root = build_workspace(tmp_path)
    refs = workflows.parse_clone_refs((root / "python-docx/.github/workflows/ci.yml").read_bytes())
    assert refs == [{"url": "https://github.com/ooxml-stack/ooxml-native-corpus.git", "line": 7}]


def test_workflow_jobs_reads_matrix_and_run_blocks(tmp_path):
    root = build_workspace(tmp_path)
    jobs = workflows.parse_workflow_jobs((root / "ooxml-core/.github/workflows/full.yml").read_bytes())
    job = jobs["full"]
    assert job["name"] == "full gate"
    assert job["if"] == "github.event_name == 'push'"
    assert job["runs_on"] == "ubuntu-latest"
    assert job["matrix"] == {"python-version": ["3.12"]}
    assert job["steps"][1]["run"] == "make full\nmake check\n"


def test_workflow_jobs_keeps_step_cwd_and_ignores_with_keys(tmp_path):
    root = build_workspace(tmp_path)
    jobs = workflows.parse_workflow_jobs((root / "ooxml-core/.github/workflows/full.yml").read_bytes())
    step = jobs["full"]["steps"][2]
    assert step["name"] == "cwd step"
    assert step["cwd"] == "sub"
    assert step["run"] == "pytest"


def test_workflow_jobs_handles_a_block_scalar_on_the_dash_line():
    data = b"jobs:\n  j:\n    steps:\n      - run: |\n          echo hi\n          echo bye\n"
    jobs = workflows.parse_workflow_jobs(data)
    assert jobs["j"]["steps"][0]["run"] == "echo hi\necho bye\n"


def test_workflow_jobs_captures_job_and_step_env():
    jobs = workflows.parse_workflow_jobs(WORKFLOW_FULL_ENV.encode("utf-8"))
    job = jobs["full"]
    assert job["env"] == {"UV_PYTHON": "3.12", "UV_GIT_PREFER_CLI": "true"}
    assert job["steps"][0]["env"] == {"NEEDS_JSON": "${{ toJSON(needs) }}"}


def test_workflow_jobs_captures_inline_env():
    data = b'jobs:\n  j:\n    env: {UV_PYTHON: "3.12"}\n    steps:\n      - run: x\n'
    jobs = workflows.parse_workflow_jobs(data)
    assert jobs["j"]["env"] == {"UV_PYTHON": "3.12"}


def _edge_case_job() -> dict:
    return workflows.parse_workflow_jobs(WORKFLOW_ENV_EDGE_CASES.encode("utf-8"))["full"]


def test_env_keeps_commas_and_actions_expressions_intact():
    """A comma inside a quoted value or a ``${{ }}`` expression is not a separator."""
    env = _edge_case_job()["env"]
    assert env["OPTIONS"] == "a,b"
    assert env["EXPRESSION"] == "${{ format('{0},{1}', github.sha, github.ref) }}"


def test_env_keeps_escaped_quotes_and_commas():
    """Case b: an escaped quote inside a flow mapping must not truncate the value."""
    assert _edge_case_job()["steps"][3]["env"] == {"MESSAGE": 'say "hello,world"', "OTHER": "ok"}


def test_env_keeps_trailing_comments_out_of_values():
    """Cases a and e: a comment after a flow mapping or a scalar is not data."""
    job = _edge_case_job()
    assert job["env"]["TRAILING"] == "a,b"
    assert job["env"]["BLOCK_COMMENT"] == "first\nsecond"
    assert job["steps"][2]["env"] == {"UV_PYTHON": "3.10"}


def test_env_folds_folded_blocks():
    """Case c: ``>-`` folds its lines into one space-separated value."""
    assert _edge_case_job()["env"]["FOLDED"] == "--first --second"


def test_env_honours_block_chomping():
    """Case d: ``|`` keeps one newline, ``|-`` strips it, ``|+`` keeps it."""
    env = _edge_case_job()["env"]
    assert env["LITERAL"] == "first\nsecond\n"
    assert env["STRIPPED"] == "first\nsecond"
    assert env["KEPT"] == "first\nsecond\n"


def test_env_on_the_dash_line_is_captured():
    steps = _edge_case_job()["steps"]
    assert steps[0]["env"] == {"INLINE": "x,y"}
    assert steps[0]["run"] == "echo one\necho two\n"
    assert steps[1]["env"] == {"FLOW": "p,q"}


def test_a_nested_env_value_is_rejected_not_coerced():
    """Actions env values are strings; a nested mapping is not a legal value."""
    parsed = workflows.parse_workflow(WORKFLOW_ENV_NESTED.encode("utf-8"))
    assert parsed["jobs"]["full"]["env"] == {}
    assert [item["code"] for item in parsed["errors"]] == ["unsupported_workflow"]
    assert "NESTED" in parsed["errors"][0]["detail"]


def test_broken_yaml_is_reported_not_guessed():
    parsed = workflows.parse_workflow(WORKFLOW_BROKEN_YAML.encode("utf-8"))
    assert parsed["jobs"] == {}
    assert [item["code"] for item in parsed["errors"]] == ["unsupported_workflow"]
    assert "invalid YAML" in parsed["errors"][0]["detail"]


def test_job_fields_do_not_depend_on_key_order():
    """Fields are read by key, so reordering a job mapping changes nothing."""
    first = (
        b"jobs:\n  j:\n    name: n\n    runs-on: ubuntu-latest\n    env: {A: '1'}\n"
        b"    steps:\n      - name: s\n        run: x\n"
    )
    second = (
        b"jobs:\n  j:\n    steps:\n      - run: x\n        name: s\n"
        b"    env: {A: '1'}\n    runs-on: ubuntu-latest\n    name: n\n"
    )
    left = workflows.parse_workflow_jobs(first)["j"]
    right = workflows.parse_workflow_jobs(second)["j"]
    for field in ("name", "runs_on", "env", "matrix", "needs", "if"):
        assert left[field] == right[field]
    assert (left["steps"][0]["name"], left["steps"][0]["run"]) == ("s", "x")
    assert (right["steps"][0]["name"], right["steps"][0]["run"]) == ("s", "x")


def test_job_and_step_bindings_carry_their_source_line():
    """Every binding must point back at the line it was read from."""
    data = (
        b"jobs:\n"
        b"  j:\n"
        b"    name: n\n"
        b"    steps:\n"
        b"      - name: first\n"
        b"        run: x\n"
        b"      - name: second\n"
        b"        run: y\n"
    )
    job = workflows.parse_workflow_jobs(data)["j"]
    assert job["line"] == 2
    assert [step["line"] for step in job["steps"]] == [5, 7]


def test_a_repeated_key_is_reported_not_last_wins():
    """Silently keeping the last value would hide a real conflict."""
    data = b'jobs:\n  j:\n    env:\n      A: "1"\n      A: "2"\n    steps:\n      - run: x\n'
    parsed = workflows.parse_workflow(data)
    assert parsed["jobs"]["j"]["env"] == {}
    assert [item["code"] for item in parsed["errors"]] == ["unsupported_workflow"]
    assert "repeats the key 'A'" in parsed["errors"][0]["detail"]


def test_a_merge_key_is_reported_not_dropped():
    """``<<`` is not an Actions construct; ignoring it would silently lose fields."""
    data = b"jobs:\n  j:\n    env:\n      <<: &b\n        A: '1'\n      B: '2'\n    steps:\n      - run: x\n"
    parsed = workflows.parse_workflow(data)
    assert [item["code"] for item in parsed["errors"]] == ["unsupported_workflow"]
    assert "merge key" in parsed["errors"][0]["detail"]


def test_yaml_anchors_and_aliases_are_resolved():
    """Aliases are legal YAML and must read the same as the anchor they point at."""
    data = (
        b"jobs:\n"
        b"  j:\n"
        b"    env: &e\n"
        b'      A: "1"\n'
        b"    steps:\n"
        b"      - run: x\n"
        b"      - env: *e\n"
        b"        run: y\n"
    )
    job = workflows.parse_workflow_jobs(data)["j"]
    assert job["env"] == {"A": "1"}
    assert job["steps"][1]["env"] == {"A": "1"}


def test_a_custom_yaml_tag_is_reported_not_stripped():
    """Stripping ``!Ref`` would turn an unsupported construct into a plausible string."""
    parsed = workflows.parse_workflow(b"jobs:\n  j:\n    steps:\n      - run: !Ref foo\n")
    assert [item["code"] for item in parsed["errors"]] == ["unsupported_workflow"]
    assert "!Ref" in parsed["errors"][0]["detail"]
    assert parsed["jobs"]["j"]["steps"][0]["run"] is None


def test_workflow_jobs_ignores_json_like_step_keys():
    """A ``with:`` block must not overwrite step identity."""
    data = (
        b"jobs:\n"
        b"  j:\n"
        b"    steps:\n"
        b"      - name: real\n"
        b"        with:\n"
        b"          name: not-a-step-name\n"
        b"        run: pytest\n"
    )
    jobs = workflows.parse_workflow_jobs(data)
    assert jobs["j"]["steps"][0]["name"] == "real"
    assert jobs["j"]["steps"][0]["run"] == "pytest"
