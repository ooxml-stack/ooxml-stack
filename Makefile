.PHONY: evidence-hygiene repo-hygiene p97-mutation-gate p98-mutation-gate p98-coverage-budget ecosystem-inventory-deps ecosystem-plan ecosystem-plan-check ecosystem-plan-refresh ecosystem-plan-check-basis ecosystem-inventory-test runner-test worktree workspace-init lint typecheck

# The inventory tool runs only against its pinned interpreter. `--write` and
# `--check` refuse to start when the versions do not match the declaration.
ECOSYSTEM_VENV ?= .venv-ecosystem-inventory
ECOSYSTEM_PYTHON ?= $(ECOSYSTEM_VENV)/bin/python
export WORKSPACE TASK REPOSITORY OWNER RETIRE_WHEN REVISION

workspace-init:
	@python3 -m scripts.workspace_agents --workspace "$$WORKSPACE"

worktree:
	@python3 -m scripts.dev_worktree --workspace "$$WORKSPACE" --task "$$TASK" --repository "$$REPOSITORY" --owner "$$OWNER" --retire-when "$$RETIRE_WHEN" --revision "$${REVISION:-HEAD}"

evidence-hygiene:
	@python3 scripts/check_evidence_retention.py

ecosystem-inventory-deps:
	@python3 -m venv $(ECOSYSTEM_VENV)
	@$(ECOSYSTEM_VENV)/bin/python -m pip install --quiet --upgrade pip
	@$(ECOSYSTEM_VENV)/bin/python -m pip install --quiet -r ci/ecosystem-inventory-test-requirements.txt

# `ecosystem-plan` reads whatever this workspace holds - use it to scan a
# specific checkout. The published plan is defined against each node's default
# branch, so refreshing it needs a workspace built that way; these two targets
# prepare one from the policy instead of assuming the caller's branches.
ecosystem-plan:
	@$(ECOSYSTEM_PYTHON) -m scripts.ooxml_ci --write

ecosystem-plan-check:
	@$(ECOSYSTEM_PYTHON) -m scripts.ooxml_ci --check

ecosystem-plan-refresh:
	@$(ECOSYSTEM_PYTHON) -m scripts.ooxml_ci.refresh --write

ecosystem-plan-check-basis:
	@$(ECOSYSTEM_PYTHON) -m scripts.ooxml_ci.refresh --check

ecosystem-inventory-test:
	@$(ECOSYSTEM_PYTHON) -m pytest tests/test_ecosystem_*.py -q

# The shared runner's own contract. These tests never start Docker; they cover
# identity, plan binding, adapter loading, the stage protocol and report
# verification, which is where a false pass would come from.
runner-test:
	@$(ECOSYSTEM_PYTHON) -m pytest tests/test_ooxml_runner_*.py tests/test_dev_worktree.py tests/test_workspace_agents.py -q

lint:
	python3 scripts/quality_gate.py ruff
	@python3 scripts/format_gate.py

typecheck:
	@python3 scripts/quality_gate.py pyright

repo-hygiene: evidence-hygiene
	@python3 scripts/audit_repo_hygiene.py $(if $(STRICT_HISTORY),--strict-history,)

p97-mutation-gate:
	@python3 scripts/run_p97_mutation_gate.py

p98-mutation-gate:
	@python3 scripts/run_p98_mutation_gate.py

p98-coverage-budget:
	@python3 scripts/build_p98_coverage_budget.py
