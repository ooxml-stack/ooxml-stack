.PHONY: evidence-hygiene repo-hygiene p97-mutation-gate p98-mutation-gate p98-coverage-budget ecosystem-inventory-deps ecosystem-plan ecosystem-plan-check ecosystem-plan-refresh ecosystem-plan-check-basis ecosystem-inventory-test runner-test

# The inventory tool runs only against its pinned interpreter. `--write` and
# `--check` refuse to start when the versions do not match the declaration.
ECOSYSTEM_VENV ?= .venv-ecosystem-inventory
ECOSYSTEM_PYTHON ?= $(ECOSYSTEM_VENV)/bin/python

evidence-hygiene:
	@python3 scripts/redact_release_evidence_paths.py

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
	@$(ECOSYSTEM_PYTHON) -m pytest tests/test_ooxml_runner_*.py -q

repo-hygiene: evidence-hygiene
	@python3 scripts/audit_repo_hygiene.py $(if $(STRICT_HISTORY),--strict-history,)

p97-mutation-gate:
	@python3 scripts/run_p97_mutation_gate.py

p98-mutation-gate:
	@python3 scripts/run_p98_mutation_gate.py

p98-coverage-budget:
	@python3 scripts/build_p98_coverage_budget.py