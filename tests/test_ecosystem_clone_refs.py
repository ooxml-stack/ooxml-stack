"""Clone-command detection: the parsed ``run`` scalar, never the raw source."""

from __future__ import annotations

import pytest

from ecosystem_workflows import (
    WORKFLOW_CLONE_FOLDED,
    WORKFLOW_CLONE_LITERAL,
    WORKFLOW_CLONE_SINGLE,
)
from scripts.ooxml_ci import workflows


# ------------------------------------------------------------- clone commands


@pytest.mark.parametrize(
    "data",
    [WORKFLOW_CLONE_SINGLE, WORKFLOW_CLONE_LITERAL, WORKFLOW_CLONE_FOLDED],
    ids=["single-line", "literal-block", "folded-block"],
)
def test_a_static_clone_reads_the_same_however_it_is_written(data):
    """Folding and block style are YAML concerns; the command is the same command."""
    refs = workflows.parse_clone_refs(data.encode("utf-8"))
    assert [ref["url"] for ref in refs] == [
        "https://github.com/ooxml-stack/ooxml-native-corpus.git"
    ]


def test_a_clone_line_never_leaves_the_run_node():
    """A folded scalar loses its line mapping, so the ``run`` node itself is reported."""
    folded = workflows.parse_clone_refs(WORKFLOW_CLONE_FOLDED.encode("utf-8"))
    literal = workflows.parse_clone_refs(WORKFLOW_CLONE_LITERAL.encode("utf-8"))
    single = workflows.parse_clone_refs(WORKFLOW_CLONE_SINGLE.encode("utf-8"))
    assert single[0]["line"] == 6  # the run: line, which is also the command line
    assert literal[0]["line"] == 7  # literal blocks keep a one-to-one mapping
    assert folded[0]["line"] == 6  # no precise mapping exists, so no line is invented


def test_existing_clone_forms_are_preserved():
    """Quoted URLs, options and a leading assignment must all still be found."""
    data = (
        b"jobs:\n  j:\n    steps:\n"
        b'      - run: git clone "https://github.com/ooxml-stack/ooxml-native-corpus.git" ../corpus\n'
        b"      - run: cd /tmp && git clone --branch v1.0.0 https://github.com/ooxml-stack/ooxml-core.git\n"
        b"      - run: GIT_TERMINAL_PROMPT=0 git clone https://github.com/ooxml-stack/ooxml-test-framework.git\n"
    )
    assert [ref["url"] for ref in workflows.parse_clone_refs(data)] == [
        "https://github.com/ooxml-stack/ooxml-native-corpus.git",
        "https://github.com/ooxml-stack/ooxml-core.git",
        "https://github.com/ooxml-stack/ooxml-test-framework.git",
    ]


MENTIONED_CLONES = [
    (
        "next-step-name",
        b"jobs:\n  j:\n    steps:\n      - run: |\n          echo ok\n"
        b"      - name: git clone https://github.com/ooxml-stack/never.git\n        run: echo ok\n",
    ),
    (
        "yaml-comment",
        b"jobs:\n  j:\n    steps:\n      - run: |\n"
        b"          # git clone https://github.com/ooxml-stack/never.git\n          echo ok\n",
    ),
    (
        "shell-comment",
        b"jobs:\n  j:\n    steps:\n      - run: |\n"
        b"          echo ok # git clone https://github.com/ooxml-stack/never.git\n",
    ),
    (
        "echo-text",
        b'jobs:\n  j:\n    steps:\n      - run: echo "git clone https://github.com/ooxml-stack/never.git"\n',
    ),
    (
        "with-value",
        b"jobs:\n  j:\n    steps:\n      - uses: actions/checkout@v4\n        with:\n"
        b"          note: git clone https://github.com/ooxml-stack/never.git\n",
    ),
    (
        "local-path",
        b"jobs:\n  j:\n    steps:\n      - run: git clone ../sibling-repo\n",
    ),
]


@pytest.mark.parametrize(
    "data", [case for _, case in MENTIONED_CLONES], ids=[name for name, _ in MENTIONED_CLONES]
)
def test_text_that_merely_mentions_a_clone_is_not_a_clone(data):
    parsed = workflows.parse_workflow(data)
    assert parsed["clone_refs"] == []
    assert parsed["errors"] == []


# ------------------------------------------------- quoted text is not syntax


def _run(body: str) -> bytes:
    """A one-step workflow whose ``run`` is a literal block holding ``body``."""
    lines = "".join(f"          {line}\n" for line in body.splitlines())
    return f"jobs:\n  j:\n    steps:\n      - run: |\n{lines}".encode("utf-8")


QUOTED_TEXT = [
    ("quoted-semicolon", "echo ';' git clone https://github.com/ooxml-stack/never.git"),
    ("quoted-ampersand", "echo '&&' git clone https://github.com/ooxml-stack/never.git"),
    ("quoted-pipe", "echo '|' git clone https://github.com/ooxml-stack/never.git"),
    ("escaped-semicolon", "echo \\; git clone https://github.com/ooxml-stack/never.git"),
    ("escaped-ampersand", "echo \\&\\& git clone https://github.com/ooxml-stack/never.git"),
    ("plain-echo-text", "echo git clone https://github.com/ooxml-stack/never.git"),
    (
        "multiline-double-quoted",
        'echo "example:\ngit clone https://github.com/ooxml-stack/never.git\n"',
    ),
    (
        "multiline-single-quoted",
        "echo 'example:\ngit clone https://github.com/ooxml-stack/never.git\n'",
    ),
]


@pytest.mark.parametrize(
    "body", [body for _, body in QUOTED_TEXT], ids=[name for name, _ in QUOTED_TEXT]
)
def test_ordinary_text_never_becomes_a_clone(body):
    """A control operator is syntax only where the grammar says so, not when quoted."""
    parsed = workflows.parse_workflow(_run(body))
    assert parsed["clone_refs"] == []
    assert parsed["errors"] == []


# --------------------------------------------------- a real clone still counts


def test_a_real_clone_after_a_quoted_semicolon_is_still_found():
    data = _run(
        "echo ';' git clone https://github.com/ooxml-stack/never.git\n"
        "git clone --depth 1 https://github.com/ooxml-stack/ooxml-native-corpus.git"
    )
    assert [ref["url"] for ref in workflows.parse_clone_refs(data)] == [
        "https://github.com/ooxml-stack/ooxml-native-corpus.git"
    ]


def test_a_real_clone_after_a_multiline_quote_is_still_found():
    data = _run(
        'echo "example:\n'
        "git clone https://github.com/ooxml-stack/never.git\n"
        '"\n'
        "git clone --depth 1 https://github.com/ooxml-stack/ooxml-native-corpus.git"
    )
    refs = workflows.parse_clone_refs(data)
    assert [ref["url"] for ref in refs] == [
        "https://github.com/ooxml-stack/ooxml-native-corpus.git"
    ]
    # ``run:`` is line 4, so the block's fourth line is line 8.
    assert [ref["line"] for ref in refs] == [8]


@pytest.mark.parametrize(
    "body",
    [
        "echo ok; git clone https://github.com/ooxml-stack/ooxml-core.git",
        "echo ok && git clone https://github.com/ooxml-stack/ooxml-core.git",
        "echo ok || git clone https://github.com/ooxml-stack/ooxml-core.git",
        "echo ok\ngit clone https://github.com/ooxml-stack/ooxml-core.git",
    ],
    ids=["semicolon", "and", "or", "newline"],
)
def test_a_real_separator_still_starts_a_new_command(body):
    assert [ref["url"] for ref in workflows.parse_clone_refs(_run(body))] == [
        "https://github.com/ooxml-stack/ooxml-core.git"
    ]
