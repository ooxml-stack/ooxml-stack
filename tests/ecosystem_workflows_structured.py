"""Workflow YAML fixtures for structured/matrix validation cases."""

from __future__ import annotations

WORKFLOW_MATRIX_DUPLICATE_KEY = """\
name: full
on: [push]
jobs:
  full:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.10"]
        python: ["3.12"]
    steps:
      - run: make full
"""

WORKFLOW_MATRIX_CUSTOM_TAG = """\
name: full
on: [push]
jobs:
  full:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: [!Ref "3.12"]
    steps:
      - run: make full
"""

WORKFLOW_LEGAL_MATRIX = """\
name: full
on: [push]
jobs:
  full:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.10", "3.12"]
        os: [ubuntu-latest]
        include:
          - python: "3.12"
            os: ubuntu-latest
        exclude:
          - python: "3.10"
    steps:
      - run: make full
"""