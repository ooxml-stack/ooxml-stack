"""Workflow fixtures for Actions expressions and shell escapes in clones.

Each fixture is a python-docx workflow whose only clone comes from the step
under test, so a missing edge cannot be masked by another one.
"""

from __future__ import annotations

CORPUS = "https://github.com/ooxml-stack/ooxml-native-corpus.git"
CORE = "https://github.com/ooxml-stack/ooxml-core.git"


def docx_workflow(body: str, indicator: str = "|-") -> str:
    """A one-step python-docx workflow whose literal-block ``run`` holds ``body``."""
    lines = "".join(f"          {line}\n" for line in body.splitlines())
    return (
        "name: ci\n"
        "on: [push]\n"
        "jobs:\n"
        "  ci:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        f"      - run: {indicator}\n"
        f"{lines}"
    )


WORKFLOW_EXPR_STATIC = docx_workflow(f"git clone {CORPUS}")
WORKFLOW_EXPR_DYNAMIC_BRANCH = docx_workflow(f"git clone --branch ${{{{ inputs.ref }}}} {CORPUS}")
WORKFLOW_EXPR_FORMAT_STRIP = docx_workflow(
    "echo \"${{ format('{0}', github.ref) }}\"\n" f"git clone {CORPUS}", "|-"
)
WORKFLOW_EXPR_FORMAT_KEEP = docx_workflow(
    "echo \"${{ format('{0}', github.ref) }}\"\n" f"git clone {CORPUS}", "|"
)
WORKFLOW_EXPR_ESCAPED = docx_workflow(
    "git clone https://github.com/ooxml-stack/ooxml\\-native-corpus.git"
)
WORKFLOW_EXPR_VAR_REPO = docx_workflow("git clone https://github.com/ooxml-stack/${REPO}.git")
WORKFLOW_EXPR_ACTIONS_REPO = docx_workflow(
    "git clone https://github.com/ooxml-stack/${{ inputs.repo }}.git"
)
WORKFLOW_EXPR_VAR_REPO_THEN_STATIC = docx_workflow(
    f"git clone https://github.com/ooxml-stack/${{{{ inputs.repo }}}}.git\ngit clone {CORE}"
)
WORKFLOW_EXPR_UNREADABLE = docx_workflow("if [ -f x ]; then\n  echo hi")
WORKFLOW_EXPR_QUOTED_STATIC = docx_workflow(f'git clone "{CORPUS}"')
WORKFLOW_EXPR_QUOTED_VAR_REPO = docx_workflow('git clone "https://github.com/ooxml-stack/${REPO}.git"')
WORKFLOW_EXPR_QUOTED_ACTIONS_REPO = docx_workflow(
    'git clone "https://github.com/ooxml-stack/${{ inputs.repo }}.git"'
)
WORKFLOW_EXPR_QUOTED_DYNAMIC_THEN_STATIC = docx_workflow(
    f'git clone "https://github.com/ooxml-stack/${{{{ inputs.repo }}}}.git"\ngit clone {CORE}'
)
WORKFLOW_EXPR_EQUALS_BRANCH = docx_workflow(
    f"git clone --branch=${{{{ inputs.ref }}}} {CORPUS}"
)
WORKFLOW_EXPR_EQUALS_DEPTH = docx_workflow(
    f"git clone --depth=${{{{ inputs.depth }}}} {CORPUS}"
)
# A run body may legitimately spell the placeholder; it must not be read as a mask.
WORKFLOW_EXPR_LITERAL_MARKER = docx_workflow("git clone __ooxml_actions_expr_0__")
WORKFLOW_EXPR_MARKER_COLLISION = docx_workflow(
    "echo __ooxml_actions_expr_0__\n"
    "git clone https://github.com/ooxml-stack/${{ inputs.repo }}.git"
)
WORKFLOW_EXPR_QUOTED_THEN_CLONE = docx_workflow(
    f"echo ';' git clone https://github.com/ooxml-stack/never.git\ngit clone --depth 1 {CORPUS}"
)
WORKFLOW_EXPR_MULTILINE_THEN_CLONE = docx_workflow(
    f'echo "example:\ngit clone https://github.com/ooxml-stack/never.git\n"\ngit clone --depth 1 {CORPUS}'
)