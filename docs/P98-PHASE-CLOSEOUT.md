# P98 Phase Closeout

Date: 2026-08-26
Branch: `main` (P98 compatibility-contract evidence slice)

## Closeout Decision

`ooxml-stack` can phase-close the P98 slice.

P98 extends the P97 mutation evidence into the four highest-risk complex rule
families that were previously left `uncovered_in_p97`. It also stands up a
tracked mutation-coverage budget (P98-C) so later phases must either reduce the
uncovered count or explicitly defer a family, and it records a best-effort
native-Office open check (P98-B) for representative outputs; the live run was
blocked by a missing macOS Automation/Accessibility consent and is recorded as
an environment blocker, not as a compatibility claim.

This is a measured compatibility-contract evidence step, not a full OOXML or
native-Office compatibility claim.

## P98-A: High-Risk Uncovered Rule Families (mutation)

Added 13 mutation cases proving 12 newly-uncovered rule ids across docx,
pptx, and xlsx, concentrated in the previously-uncovered complex families:

| Family | Rules now proven |
| --- | --- |
| ChartEx | `chartex_mc_wrapper`, `chartex_strdim_order`, `chartex_style_id` (pptx + docx) |
| SmartArt / diagram relations | `smartart_drawing_part` (pptx) |
| Embedded package / media relations | `chart_embedded_xlsx`, `media_rel_integrity` (pptx); `hyperlink_rel_valid`, `header_footer_rel_valid`, `document_rels_required` (docx) |
| Spreadsheet slicer | `workbook_slicer_cache_structure`, `slicer_part_contract`, `slicer_cache_definition_consistency` (xlsx) |

Gate result:

- Mutation cases: 13
- Passed: 13 (0 failed)
- Format-rule pairs never before covered: 13
- Unique rules proven (net new vs P97, format-agnostic): 12
- docx 4 / pptx 6 / xlsx 3

Every target rule was `uncovered_in_p97`, so P98-A is net-new negative evidence,
not a re-derivation of P97.

### Files

- `scripts/p98_mutation_cases.py` — 13 control/mutant packages.
- `scripts/run_p98_mutation_gate.py` — runner producing evidence + manifest.
- `tests/test_p98_mutation_gate.py` — 7 tests.
- `release-profiles/p98-rule-coverage-mutation.json` — locked profile.
- `release-evidence/p98/rule-coverage-mutation-gate-summary.json`, `manifest.json`.

Validation:

- `make p98-mutation-gate` -> 13/13 passed
- `python3 -m pytest tests` -> 366 passed

Evidence retention:

- P98-A does **not** persist any Office package under `release-evidence/`: the
  gate writes each control/mutant docx/pptx/xlsx into a throwaway temp dir and
  records only JSON evidence (`summary.json`, `manifest.json`,
  `coverage-budget-baseline.json`, office verification results). The Evidence
  Retention check (`make evidence-hygiene`, `check_evidence_retention.py`)
  passes with no `RETAINED-ARTIFACTS.txt` P98 entry, which is documented in a
  comment in that allowlist file.

## P98-B — Native Office Live-Open Check (environment blocker)

Microsoft Word / PowerPoint / Excel are installed on this host. A lightweight
macOS AppleScript harness was built to open representative generated outputs and
record `pass` / `repair_dialog` / `crash_error` / `timeout`.

- `scripts/run_p98_office_check.py`
- `release-evidence/p98/office-verification/office-verification-results.json`
- `tests/test_p98_office_check.py`

Outcome (recorded precisely):

- The live open could NOT be driven to a defined result because the host did not
  grant the macOS Automation/Accessibility consent required to read Office
  state and scan system dialogs — every Office query returned
  `-10004 A privilege violation occurred`.
- All four representative files therefore report `blocked_automation_permission`.
  This is an environment blocker, **not** a pass and **not** a repair-dialog
  result. No `pass` claim is made from P98-B.

Boundaries (do not over-claim):

- No native-Office `pass`, `repair_dialog`, `crash`, or `timeout` result is
  claimed from P98-B because the automation permission is not granted on this
  host.
- Re-running the harness on a host with macOS Automation/Accessibility consent
  is the required next step to obtain per-file `pass` / `repair_dialog` evidence.
- `pass_with_dialog`, recovery, and macro prompts are separate statuses and are
  never folded into a compatibility claim.

## P98-C — Mutation-Coverage Budget

Turned the uncovered-mutation set into a tracked baseline.

- P97 documented historical baseline: 76 uncovered rules (docx 31, pptx 29,
  xlsx 16).
- P98-A proves 13 format-rule pairs (12 unique ids).
- Current registry-counted uncovered baseline: **59** (docx 25, pptx 22,
  xlsx 12). The small gap versus simply subtracting P98's proofs from 76
  reflects registry-set drift since P97; the budget anchors to the live registry
  so it stays runnable.

Deferred families recorded with reasons:

- docx `word_drawing_geometry` (5 rules) — needs non-tutored drawing-shape
  negative fixtures in a dedicated later phase.
- pptx `presentation_animation` (2 rules) — needs realistic timing/trigger parts.

Budget rule: each follow-up phase must reduce `total_uncovered` in
`release-evidence/p98/coverage-budget-baseline.json` or explicitly defer a
family with a reason; no new broad compatibility claim may exceed what the
measured mutation evidence supports.

### Files

- `scripts/build_p98_coverage_budget.py`
- `release-evidence/p98/coverage-budget-baseline.json`
- `tests/test_p98_coverage_budget.py` (4 tests)
- Makefile targets: `p98-mutation-gate`, `p98-coverage-budget`

## Boundaries

Keep these claims:

- P96 compliance-clean profiles remain unchanged.
- P97 proves 21 mutation cases / 16 unique rules.
- P98 proves 13 mutation cases / 12 new unique rules in the four complex
  uncovered families.
- Rules still uncovered in the P98-C budget are outside this claim surface.

Do not claim:

- Full OOXML compatibility.
- Full native-Office compatibility.
- Complete mutation coverage for every registered rule.
- Semantic-editability count increases from P98.

## Next Steps

- Reduce the 59-uncovered budget by adding mutation fixtures for the next
  highest-risk uncovered families (e.g., OMML math after the docx math slice,
  and the deferred `word_drawing_geometry` / `presentation_animation` groups).
- Re-run `scripts/run_p98_office_check.py` on a host where macOS
  Automation/Accessibility consent is granted, so P98-B yields per-file
  `pass` / `repair_dialog` evidence instead of the environment blocker, then
  extend it into a repair-dialog-as-blocker gate for checker-reported-clean
  files and re-open the same output set at release time.