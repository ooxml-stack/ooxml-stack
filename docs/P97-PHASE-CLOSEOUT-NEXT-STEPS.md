# P97 Phase Closeout And Next Steps

Date: 2026-08-06
Branch: `compatibility-contract-p97-rule-coverage`
Current head: `dcabcaf6`

## Closeout Decision

`ooxml-projects` can phase-close this slice.

The phase is complete as a measured compatibility-contract evidence step, not
as a full OOXML compatibility claim. The stack now has:

- P96 compliance-clean profile for docx, pptx, and xlsx.
- P97 expanded mutation gate proving selected compliance rules fail closed.
- P97 evidence provenance fixed so generated evidence does not point at a stale
  self commit.
- P97 metric wording fixed: 21 proven format-rule pairs, 16 unique rule IDs.
- Local validation green on the stack repo.

## Current Measured State

P97 profile:

- Mutation cases: 21
- Passed mutation cases: 21
- Failed mutation cases: 0
- Format-rule pairs proven: 21
- Unique rule IDs proven: 16
- docx: 7/7
- pptx: 7/7
- xlsx: 7/7

Evidence:

- `release-profiles/p97-rule-coverage-mutation.json`
- `release-evidence/p97/rule-coverage-mutation-gate-summary.json`
- `release-evidence/p97/manifest.json`
- `scripts/run_p97_mutation_gate.py`
- `scripts/p97_mutation_cases.py`
- `tests/test_p97_mutation_gate.py`

Latest validation:

- `make p97-mutation-gate` -> 21/21 passed
- `python3 -m pytest tests/test_p97_mutation_gate.py` -> 6 passed
- `python3 -m pytest tests` -> 338 passed
- `make evidence-hygiene` -> passed

## What This Means

This phase proves the compliance layer is no longer just reporting clean
profiles. It now has negative mutation evidence showing representative rules
actually alarm on malformed packages across docx, pptx, and xlsx.

This is enough to stop the current P96/P97 readiness loop and hand off to a
new phase.

## Boundaries

Do not claim:

- Full OOXML compatibility.
- Full native Office compatibility.
- Complete mutation coverage for every registered rule.
- Semantic-editability count increases from P97.
- Native Office replay coverage from P97.

Keep these claims:

- P96 is compliance-clean under the documented registered-rule profile.
- P97 proves representative mutation alarm paths across three formats.
- Rules still marked `uncovered_in_p97` remain outside the P97 mutation claim.

## Next Steps

### P98-A: High-Risk Uncovered Rule Family

Recommended next phase.

Add targeted mutation fixtures for the complex uncovered families:

- ChartEx rules.
- SmartArt / diagram relationship rules.
- Spreadsheet slicer rules.
- Additional embedded package/media relationship rules.

Target output:

- 6-10 new mutation cases.
- At least one complex family per format where applicable.
- Updated P98 profile and evidence.
- Full stack tests green.

This is the best next step because it reduces the highest false-green risk
without changing the claim surface.

### P98-B: Native Office Live-Test Risk

Run or bind real Office evidence for representative generated outputs.

Target output:

- Word/PowerPoint/Excel open without repair dialogs for selected P96/P97 outputs.
- Explicit status for pass, pass_with_dialog, repair_dialog, crash, timeout.
- No silent upgrade from static compliance to native compatibility.

This is valuable but operationally heavier because it depends on local Office
automation and machine state.

### P98-C: Mutation Coverage Budget

Turn uncovered mutation coverage into a tracked budget.

Target output:

- Record current `uncovered_in_p97` counts as baseline.
- Require each follow-up phase to reduce uncovered count or explicitly defer a
  family with reason.
- Prevent future profiles from adding broad claims without reducing risk.

This is useful if the project will continue many small compatibility phases.

### P99: Public Release Hygiene

Only after P98 direction is chosen.

Target output:

- Confirm public-safe current tree.
- Decide whether to use current repo history or a fresh public mirror.
- Keep large/private historical evidence out of public release paths.

## Recommended Stop Point

Stop now at P97 if the goal is a clean phase boundary.

Resume with P98-A when ready. It is the most direct continuation from the
current evidence and should not require changing core implementation repos
unless a rule defect is found while building fixtures.
