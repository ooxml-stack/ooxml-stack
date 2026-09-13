"""Workflow YAML fixtures shared by the ecosystem inventory tests."""

from __future__ import annotations

WORKFLOW_FULL = """\
name: full
on: [push]
jobs:
  full:
    name: full gate
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12"]
    steps:
      - uses: actions/checkout@v4
      - name: run
        run: |
          make full
          make check
      - name: cwd step
        working-directory: sub
        run: pytest
        with:
          name: not-a-step-name
"""

WORKFLOW_DOCX = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - uses: ooxml-stack/ooxml-stack/.github/workflows/plan.yml@v1.0.0
      - run: git clone --depth 1 https://github.com/ooxml-stack/ooxml-native-corpus.git ../corpus
"""

WORKFLOW_DOCX_FLOATING = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - uses: ooxml-stack/ooxml-stack/.github/workflows/plan.yml@main
"""

WORKFLOW_DOCX_TAG = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - uses: ooxml-stack/ooxml-stack/.github/workflows/plan.yml@v1.0.0
"""

WORKFLOW_DOCX_UNKNOWN = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - uses: ooxml-stack/ooxml-new/.github/workflows/plan.yml@main
"""

WORKFLOW_DOCX_THIRD_PARTY = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - uses: actions/checkout@v4
"""

WORKFLOW_DOCX_OTHER_ORG = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - uses: other-org/ooxml-stack/.github/workflows/plan.yml@v1.0.0
"""

WORKFLOW_TWO_ORGS = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - uses: ooxml-stack/ooxml-stack/.github/workflows/plan.yml@v1.0.0
      - uses: other-org/ooxml-stack/.github/workflows/plan.yml@v1.0.0
"""

WORKFLOW_TWO_ORGS_REVERSED = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - uses: other-org/ooxml-stack/.github/workflows/plan.yml@v1.0.0
      - uses: ooxml-stack/ooxml-stack/.github/workflows/plan.yml@v1.0.0
"""

WORKFLOW_FULL_ENV = """\
name: full
on: [push]
jobs:
  full:
    runs-on: ubuntu-latest
    env:
      UV_PYTHON: "3.12"
      UV_GIT_PREFER_CLI: true
    steps:
      - name: run
        env:
          NEEDS_JSON: ${{ toJSON(needs) }}
        run: make full
"""

WORKFLOW_ENV_EDGE_CASES = """\
name: full
on: [push]
jobs:
  full:
    runs-on: ubuntu-latest
    env:
      OPTIONS: "a,b"
      EXPRESSION: ${{ format('{0},{1}', github.sha, github.ref) }}
      FOLDED: >-
        --first
        --second
      LITERAL: |
        first
        second
      STRIPPED: |-
        first
        second
      KEPT: |+
        first
        second
      TRAILING: a,b # comment
      BLOCK_COMMENT: |- # comment
        first
        second
    steps:
      - env:
          INLINE: "x,y"
        run: |
          echo one
          echo two
      - env: {FLOW: "p,q"}
        run: make full
      - name: commented flow
        env: {UV_PYTHON: "3.10"} # choose Python
        run: make full
      - name: escaped
        env: {MESSAGE: "say \\"hello,world\\"", OTHER: "ok"}
        run: make full
"""

# GitHub Actions env values are strings; a nested mapping is not a legal value.
WORKFLOW_ENV_NESTED = """\
name: full
on: [push]
jobs:
  full:
    runs-on: ubuntu-latest
    env:
      NESTED:
        inner: value
    steps:
      - run: make full
"""

WORKFLOW_BROKEN_YAML = """\
name: ci
jobs:
  test:
    steps:
      - uses: [unclosed
"""

# ------------------------------------------------------------- clone commands
# The same static command written three ways must read the same.

WORKFLOW_CLONE_SINGLE = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - run: git clone --depth 1 https://github.com/ooxml-stack/ooxml-native-corpus.git ../corpus
"""

WORKFLOW_CLONE_LITERAL = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - run: |
          git clone --depth 1 https://github.com/ooxml-stack/ooxml-native-corpus.git ../corpus
"""

WORKFLOW_CLONE_FOLDED = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - run: >-
          git
          clone --depth 1 https://github.com/ooxml-stack/ooxml-native-corpus.git ../corpus
"""

# Text that merely mentions a clone must never become a dependency edge.
WORKFLOW_MENTIONS_CLONE = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - run: |
          echo ok
      - name: git clone https://github.com/ooxml-stack/never-existed.git
        run: echo ok
"""

# A quoted separator is ordinary text; the real clone on the next line still counts.
WORKFLOW_CLONE_QUOTED_MIXED = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - run: |
          echo ';' git clone https://github.com/ooxml-stack/never-existed.git
          git clone --depth 1 https://github.com/ooxml-stack/ooxml-native-corpus.git ../corpus
"""

# A newline inside quotes does not end the command, so the example stays echo text.
WORKFLOW_CLONE_MULTILINE_QUOTED_MIXED = '''\
name: ci
on: [push]
jobs:
  test:
    steps:
      - run: |
          echo "example:
          git clone https://github.com/ooxml-stack/never-existed.git
          "
          git clone --depth 1 https://github.com/ooxml-stack/ooxml-native-corpus.git ../corpus
'''

# The fake target is a real policy node, so only the grammar keeps it out.
WORKFLOW_CLONE_QUOTED_DECLARED = """\
name: ci
on: [push]
jobs:
  test:
    steps:
      - run: |
          echo '|' git clone https://github.com/ooxml-stack/ooxml-core.git
          git clone --depth 1 https://github.com/ooxml-stack/ooxml-native-corpus.git ../corpus
"""

# ------------------------------------------------------- structured validation
# Re-exported so callers keep a single import surface for workflow fixtures.
from ecosystem_workflows_structured import (  # noqa: E402,F401
    WORKFLOW_LEGAL_MATRIX,
    WORKFLOW_MATRIX_CUSTOM_TAG,
    WORKFLOW_MATRIX_DUPLICATE_KEY,
)