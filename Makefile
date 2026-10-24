.PHONY: coverage evidence-hygiene repo-hygiene p97-mutation-gate p98-mutation-gate p98-coverage-budget ecosystem-inventory-deps ecosystem-plan ecosystem-plan-check ecosystem-plan-refresh ecosystem-plan-check-basis ecosystem-inventory-test runner-test worktree workspace-init lint typecheck native-dev native-test native-release native-release-local native-wheelhouse

# The inventory tool runs only against its pinned interpreter. `--write` and
# `--check` refuse to start when the versions do not match the declaration.
ECOSYSTEM_VENV ?= .venv-ecosystem-inventory
ECOSYSTEM_PYTHON ?= $(ECOSYSTEM_VENV)/bin/python
NATIVE_RELEASE_CONFIG ?= release/native-macos-arm64.yaml
NATIVE_RELEASE_PYTHON ?= $(ECOSYSTEM_PYTHON)
NATIVE_WHEELHOUSE ?= $(CURDIR)/../.delivery-evidence/artifacts/native/wheelhouse
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

coverage:
	@$(ECOSYSTEM_PYTHON) -m coverage run --source=ooxml_runner -m pytest tests/test_ooxml_runner_*.py -q
	@$(ECOSYSTEM_PYTHON) -m coverage report

lint:
	python3 scripts/quality_gate.py ruff
	@python3 scripts/format_gate.py
	python3 scripts/check_action_pins.py
	python3 scripts/check_dependency_notices.py
	python3 scripts/size_report.py --check
	python3 scripts/check_evidence_redaction.py

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

native-dev:
	@$(NATIVE_RELEASE_PYTHON) -m scripts.native_release dev --config $(NATIVE_RELEASE_CONFIG)

native-test:
	@test -n "$(CANDIDATE)" || (echo "CANDIDATE is required; use CANDIDATE=/absolute/path or CANDIDATE=latest-dev" >&2; exit 2)
	@$(NATIVE_RELEASE_PYTHON) -m scripts.native_release test --config $(NATIVE_RELEASE_CONFIG) --candidate "$(CANDIDATE)" $(if $(INTERNAL_LICENSE),--internal-license,)

native-release:
	@$(NATIVE_RELEASE_PYTHON) -m scripts.native_release release --config $(NATIVE_RELEASE_CONFIG)

native-wheelhouse:
	@test -n "$(NATIVE_WHEELHOUSE)" || (echo "NATIVE_WHEELHOUSE is required" >&2; exit 2)
	@$(NATIVE_RELEASE_PYTHON) -m scripts.native_release build-wheelhouse --config $(NATIVE_RELEASE_CONFIG) --wheelhouse "$(NATIVE_WHEELHOUSE)"

native-release-local:
	@$(NATIVE_RELEASE_PYTHON) -m scripts.native_release release-local --config $(NATIVE_RELEASE_CONFIG)
