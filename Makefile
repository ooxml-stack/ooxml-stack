.PHONY: ledger dashboard dashboard-md evidence-hygiene repo-hygiene p97-mutation-gate p98-mutation-gate p98-coverage-budget campaign-schema-policy campaign-preflight campaign-gap-ledger campaign-ledgers campaign-target-queue campaign-remaining-buckets campaign-target-exclusion-audit campaign-high-yield-candidates campaign-no-semantic-discovery campaign-presence-context-candidates campaign-chunk-plan campaign-chunk-replay campaign-burndown campaign-unlock-plan campaign-close-error-diagnostics campaign-close-error-rerun campaign-close-error-exact-replay

LEDGER_OUT ?= artifacts/ooxml-element-capability-ledger.json

ledger:
	@python3 scripts/build_ooxml_element_capability_ledger.py --out $(LEDGER_OUT)

dashboard: ledger
	@python3 scripts/build_capability_dashboard_html.py --ledger $(LEDGER_OUT) $(if $(OUT),--out $(OUT),) $(if $(filter 0,$(OPEN)),,--open)

dashboard-md: ledger
	@python3 scripts/build_capability_dashboard.py --ledger $(LEDGER_OUT) $(if $(OUT),--out $(OUT),)

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

campaign-schema-policy:
	@python3 scripts/former_preserve_only_schema_policy_audit.py --write $(if $(LIMIT),--limit $(LIMIT),)

campaign-gap-ledger:
	@python3 scripts/build_former_preserve_only_semantic_campaign.py

campaign-preflight: campaign-schema-policy campaign-gap-ledger

campaign-ledgers: campaign-preflight
	@python3 scripts/former_preserve_only_hydrate_operations.py

campaign-target-queue: campaign-ledgers
	@python3 scripts/build_semantic_editability_target_queue.py

campaign-remaining-buckets: campaign-ledgers
	@python3 scripts/build_semantic_editability_remaining_buckets.py

campaign-target-exclusion-audit: campaign-target-queue campaign-remaining-buckets
	@python3 scripts/build_target_queue_exclusion_audit.py

campaign-high-yield-candidates: campaign-remaining-buckets
	@python3 scripts/build_semantic_editability_high_yield_candidates.py

campaign-no-semantic-discovery: campaign-remaining-buckets
	@python3 scripts/build_no_semantic_field_discovery.py

campaign-presence-context-candidates: campaign-no-semantic-discovery
	@python3 scripts/build_presence_context_model_candidates.py

campaign-chunk-plan: campaign-remaining-buckets
	@python3 scripts/build_semantic_editability_chunk_plan.py $(ARGS)

campaign-chunk-replay:
	@python3 scripts/former_preserve_only_promote_chunked.py $(ARGS)

campaign-burndown:
	@python3 scripts/former_preserve_only_promote_loop.py $(ARGS)

campaign-unlock-plan: campaign-remaining-buckets
	@python3 scripts/build_semantic_editability_target_queue.py
	@python3 scripts/build_target_queue_exclusion_audit.py
	@python3 scripts/build_unlock_blocker_taxonomy.py
	@python3 scripts/build_schema_policy_unlock_candidates.py
	@python3 scripts/build_family_model_unlock_candidates.py
	@python3 scripts/build_no_semantic_field_discovery.py
	@python3 scripts/build_presence_context_model_candidates.py
	@python3 scripts/build_office_boundary_analysis.py
	@python3 scripts/build_targeted_unlock_replay_plan.py

campaign-close-error-diagnostics:
	@python3 scripts/build_close_error_diagnostics.py
	@python3 scripts/build_close_error_rerun_report.py

campaign-close-error-rerun:
	@python3 scripts/run_close_error_office_rerun.py $(ARGS)

campaign-close-error-exact-replay:
	@python3 scripts/run_close_error_exact_replay.py $(ARGS)
