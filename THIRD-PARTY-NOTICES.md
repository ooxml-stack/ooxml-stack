# Third-party notices

Runtime and gate dependencies of the shared runner and its inventory tool, with
the license each is distributed under. The pinned versions live in
`ci/ecosystem-inventory-requirements.txt` and
`ci/ecosystem-inventory-test-requirements.txt`;
`scripts/check_dependency_notices.py` fails the lint gate when a pinned
dependency is missing from this table.

| Package | License | Upstream |
| --- | --- | --- |
| `packaging` | Apache-2.0 OR BSD-2-Clause | https://pypi.org/project/packaging/ |
| `PyYAML` | MIT | https://pyyaml.org/ |
| `tree-sitter` | MIT License | https://pypi.org/project/tree-sitter/ |
| `tree-sitter-bash` | MIT | https://pypi.org/project/tree-sitter-bash/ |
| `pytest` | MIT | https://pypi.org/project/pytest/ |
| `coverage` | Apache-2.0 | https://github.com/coveragepy/coveragepy |
