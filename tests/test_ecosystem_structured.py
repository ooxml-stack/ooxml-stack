"""Structured-field validation: matrix, needs and runs-on are read, not guessed."""

from __future__ import annotations

import pytest

from ecosystem_workflows import (
    WORKFLOW_LEGAL_MATRIX,
    WORKFLOW_MATRIX_CUSTOM_TAG,
    WORKFLOW_MATRIX_DUPLICATE_KEY,
)
from scripts.ooxml_ci import workflows


# ------------------------------------------------------- structured validation


def test_a_repeated_matrix_key_is_reported_not_last_wins():
    parsed = workflows.parse_workflow(WORKFLOW_MATRIX_DUPLICATE_KEY.encode("utf-8"))
    assert parsed["jobs"]["full"]["matrix"] == {}
    assert [item["code"] for item in parsed["errors"]] == ["unsupported_workflow"]
    error = parsed["errors"][0]
    assert "repeats the key 'python'" in error["detail"]
    assert "matrix" in error["where"] and "line" in error["where"]


def test_a_custom_tag_inside_the_matrix_is_reported():
    parsed = workflows.parse_workflow(WORKFLOW_MATRIX_CUSTOM_TAG.encode("utf-8"))
    assert [item["code"] for item in parsed["errors"]] == ["unsupported_workflow"]
    assert "!Ref" in parsed["errors"][0]["detail"]


@pytest.mark.parametrize("field", ["needs", "runs-on"])
def test_a_custom_tag_in_a_structured_job_field_is_reported(field):
    data = f'jobs:\n  j:\n    {field}: !Ref x\n    steps:\n      - run: y\n'.encode()
    parsed = workflows.parse_workflow(data)
    assert [item["code"] for item in parsed["errors"]] == ["unsupported_workflow"]
    assert "!Ref" in parsed["errors"][0]["detail"]


def test_a_legal_matrix_with_include_and_exclude_is_preserved():
    matrix = workflows.parse_workflow_jobs(WORKFLOW_LEGAL_MATRIX.encode("utf-8"))["full"]["matrix"]
    assert matrix["python"] == ["3.10", "3.12"]
    assert matrix["os"] == ["ubuntu-latest"]
    assert matrix["include"] == [{"python": "3.12", "os": "ubuntu-latest"}]
    assert matrix["exclude"] == [{"python": "3.10"}]


def test_an_anchor_and_alias_inside_the_matrix_are_resolved():
    data = (
        b"jobs:\n  j:\n    strategy:\n      matrix:\n"
        b"        python: &py ['3.12']\n"
        b"        include:\n          - python: *py\n"
        b"    steps:\n      - run: x\n"
    )
    matrix = workflows.parse_workflow_jobs(data)["j"]["matrix"]
    assert matrix["python"] == ["3.12"]
    assert matrix["include"] == [{"python": ["3.12"]}]


def test_a_recursive_alias_in_the_matrix_is_reported_not_hung():
    data = b"jobs:\n  j:\n    strategy:\n      matrix: &m\n        include: *m\n    steps:\n      - run: x\n"
    parsed = workflows.parse_workflow(data)
    assert [item["code"] for item in parsed["errors"]] == ["unsupported_workflow"]
    assert "recursive alias" in parsed["errors"][0]["detail"]


def test_an_actions_expression_in_the_matrix_stays_verbatim():
    data = (
        b"jobs:\n  j:\n    strategy:\n      matrix:\n"
        b'        python: ["${{ matrix.python }}"]\n'
        b"    steps:\n      - run: x\n"
    )
    matrix = workflows.parse_workflow_jobs(data)["j"]["matrix"]
    assert matrix["python"] == ["${{ matrix.python }}"]