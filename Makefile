.PHONY: evidence-hygiene repo-hygiene p97-mutation-gate p98-mutation-gate p98-coverage-budget

evidence-hygiene:
	@python3 scripts/redact_release_evidence_paths.py

repo-hygiene: evidence-hygiene
	@python3 scripts/audit_repo_hygiene.py $(if $(STRICT_HISTORY),--strict-history,)

p97-mutation-gate:
	@python3 scripts/run_p97_mutation_gate.py

p98-mutation-gate:
	@python3 scripts/run_p98_mutation_gate.py

p98-coverage-budget:
	@python3 scripts/build_p98_coverage_budget.py