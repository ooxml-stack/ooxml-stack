.PHONY: evidence-hygiene repo-hygiene p97-mutation-gate p98-mutation-gate p98-coverage-budget ecosystem-inventory-deps ecosystem-plan ecosystem-plan-check ecosystem-inventory-test

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

ecosystem-plan:
	@$(ECOSYSTEM_PYTHON) -m scripts.ooxml_ci --write

ecosystem-plan-check:
	@$(ECOSYSTEM_PYTHON) -m scripts.ooxml_ci --check

ecosystem-inventory-test:
	@$(ECOSYSTEM_PYTHON) -m pytest tests/test_ecosystem_*.py -q

repo-hygiene: evidence-hygiene
	@python3 scripts/audit_repo_hygiene.py $(if $(STRICT_HISTORY),--strict-history,)

p97-mutation-gate:
	@python3 scripts/run_p97_mutation_gate.py

p98-mutation-gate:
	@python3 scripts/run_p98_mutation_gate.py

p98-coverage-budget:
	@python3 scripts/build_p98_coverage_budget.py