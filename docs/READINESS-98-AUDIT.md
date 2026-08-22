# OOXML Readiness 98 Audit

Date: 2026-05-30

Status: **100/100 under this readiness rubric**. Core supported-valid DOCX/PPTX
open, active roundtrip, compatible preserve, native Office corpus
scale/provenance, desktop Office supported-valid repair-dialog evidence, and
fresh release-tag install evidence are all at target. Macro-enabled corpus files
are machine-classified separately from the supported-valid non-macro Office
denominator, and the native Word repair-dialog sample is quarantined rather than
counted as supported-valid release evidence.

## Score

| Area | Points | Evidence |
| --- | ---: | --- |
| Supported-valid open failures classified to 0 | 15/15 | 27 open failures classified; 0 supported-valid failures |
| Open/active roundtrip for opened supported-valid files | 25/25 | 3025/3025 active roundtrip pass |
| Exact vs compatible preserve separated and explained | 20/20 | exact 3012/3025; compatible 3025/3025; unexplained partials 0 |
| Missing parts, relationship loss, binary mutation | 10/10 | preserve compatibility evidence reports no unexplained part/rels/binary loss |
| Release gates implemented | 10/10 | schema, compat smoke, Office open, render smoke, fresh-install hooks exist |
| Office repair-dialog evidence | 10/10 | 361/361 supported-valid non-macro native Office gate pass_total; repair_dialog_count 0 |
| Native Office corpus scale/provenance | 5/5 | 370 files; 369 pass; 1 quarantined with reason; producer metadata present |
| Fresh install from release tags | 5/5 | release tags installed and imported in a fresh venv |
| **Total** | **100/100** | **Claim >=98 readiness only within the measured contract** |

## Current Compat Metrics

Run directory:
`ooxml-test-framework/tools/compat-test/results/runs/p9-strict-ns-equivalence-20260525T120000Z/`

| Metric | DOCX | PPTX | Combined |
| --- | ---: | ---: | ---: |
| Total files | 2332 | 720 | 3052 |
| Open pass | 2310 | 715 | 3025 |
| Open fail | 22 | 5 | 27 |
| Exact preserve | 2298/2310 | 714/715 | 3012/3025 |
| Compatible preserve | 2310/2310 | 715/715 | 3025/3025 |
| Unexplained preserve partial | 0 | 0 | 0 |
| Active roundtrip | 2310/2310 | 715/715 | 3025/3025 |

Open failure classification:

- total open failures: 27
- supported-valid open failures: 0
- excluded invalid: 22
- excluded encrypted: 5
- categories: corrupt ZIP 11, malformed XML 5, encrypted OLE container 5,
  mislabeled non-OOXML 4, empty file 1, invalid container 1

## New Evidence Added

| Repo | Commit | Evidence |
| --- | --- | --- |
| `ooxml-test-framework` | `e0863e7` | desktop Office open gate CLI and tests |
| `ooxml-test-framework` | `93a3d65` | DOCX/PPTX render-critical smoke gate |
| `ooxml-test-framework` | `ecae986` | fixed Office gate launch path; real 2-file smoke passed |
| `ooxml-test-framework` | `97cee36` | Office open gate closes each opened document without saving |
| `ooxml-test-framework` | `849763f` | Office gate classifies macro/security dialogs, macro timeouts, and Office crashes |
| `ooxml-test-framework` | `6386b35` | native corpus Office gate selector excludes quarantine and macro-enabled rows from supported-valid denominator |
| `ooxml-test-framework` | `d216755` | native corpus Office gate writes partial reports and supports resume |
| `ooxml-test-framework` | `9fcd1a2` | native corpus Office gate supports limited smoke runs |
| `ooxml-test-framework` | `2c4dd28` | native corpus Office gate can retry and replace blocking resume rows |
| `ooxml-test-framework` | `4c2d600` / `v0.5.14` | release tag used by full verifier and fresh install gate |
| `ooxml-core` | `2c11a9d` | release readiness gates wired into verifier |
| `ooxml-core` | `487093d` | release verifier builds clean sibling worktrees including native corpus and stack docs |
| `ooxml-core` | `fbc61b5` / `v0.3.24` | release verifier links ignored native corpus payload and passes full release stack gate |
| `ooxml-stubs` | `afb1e1e` | release pin lock drift fixed |
| `ooxml-stubs` | `787d0f3` / `v0.2.7` | release tag used by downstream fresh installs |
| `python-docx` | `b4e7b14` / `v1.2.5` | release tag passed clean worktree tests and fresh import |
| `python-pptx` | `fb8c2485` / `v2.0.5` | release tag passed clean worktree tests and fresh import |
| `ooxml-test-framework` | `a3d1754` / `v0.5.16` | P14 tag/HEAD consistency for release verifier closure |
| `ooxml-core` | `85a5b13` / `v0.3.27` | P14 tagged release verifier containing the P13 DOCX drawing regression gate |
| `ooxml-stubs` | `097bd12` / `v0.2.10` | P14 lock hash aligned to `ooxml-core v0.3.27` |
| `python-docx` | `0f1be5d` / `v1.2.6` | P14 fresh-install tag aligned to `ooxml-core v0.3.27` and `ooxml-stubs v0.2.9` |
| `python-pptx` | `f413535b` / `v2.0.7` | P14 fresh-install tag aligned to `ooxml-core v0.3.27` and `ooxml-stubs v0.2.10` |
| `ooxml-core` | `5eeb3e6` / `v0.3.28` | P15 verifier isolates private native-corpus env from ordinary clean pytest while keeping dedicated native gates active |
| `ooxml-core` | `90fa4c4` / `v0.3.29` | P16 release profile verifier freezes the P15 zero-warning evidence bundle as a checked-in profile gate |
| `ooxml-core` | `88b40b6` / `v0.3.30` | P17 locked profile verifier validates evidence SHA-256, byte sizes, and required corpus manifest before replay |
| `ooxml-core` | `ef47194` / `v0.3.34` | P19 release profile verifier enforces the P18 100-case DOCX drawing denominator, clean-root compat environments, and retried fresh tag installs |
| `python-docx` | `b749f48` / `v1.2.7` | P15 stubs native preserve gate remains valid when stubs are auto-registered by the app package |
| `python-pptx` | `e360e7f6` / `v2.0.8` | P15 stubs native preserve gate remains valid when stubs are auto-registered by the app package |
| `ooxml-native-corpus` | `d1c85d7` | native corpus expanded to 350 files with producer/version metadata |
| `ooxml-native-corpus` | `473369f` | `docx_media_dense_case` quarantined after real Word repair-dialog evidence; inspection baseline was 349 pass / 1 quarantined |
| `ooxml-native-corpus` | `abb503b` | P18 expands DOCX drawing corpus coverage to 370 rows; 369 pass / 1 quarantined; SmartArt 8 and drawing canvas 10 in regression inventory |
| `ooxml-test-framework` | `ed3e1b0` | P18 drawing regression selection defaults cover 100 cases with SmartArt target 8 and drawing canvas target 6 |
| `ooxml-test-framework` | `943f966` / `v0.5.18` | P20 machine-generates the DOCX drawing taxonomy matrix from corpus XML plus P19 selected-case evidence |
| `ooxml-test-framework` | `e43944d` / `v0.5.19` | P21/P28 expanded DOCX drawing active coverage gates, generated coverage docs, and classification cleanup |
| `ooxml-core` | `c1ebfce` / `v0.3.36` | P28 release verifier accepts expanded DOCX drawing semantic assertion counts, pins framework `v0.5.19`, and keeps release gate tests within file-size limits |
| `ooxml-stack` | `15865ae` | compatibility contract |
| `ooxml-stack` | this P19 stack commit | freezes P18 DOCX drawing evidence into a hash-validated locked profile |
| `ooxml-stack` | this P20 stack commit | stores P20 coverage matrix evidence and narrows DOCX drawing claim boundaries |
| `ooxml-stack` | `6777263` | stores P21 expanded DOCX drawing active coverage evidence |
| `ooxml-stack` | `319857d` | stores P23 full native Office gate evidence |
| `ooxml-stack` | `8ce4444` | freezes P28 expanded DOCX drawing release profile |
| `ooxml-test-framework` | `3275a06` / `v0.5.24` | P43-P51 semantic inventory, OPC graph, dashboard, public API contract, and manifest evidence tooling |
| `ooxml-core` | `1deef96` / `v0.3.41` | P51 locked profile reads semantic metric sources and shared semantic status vocabulary |
| `ooxml-stack` | this P51 stack commit | freezes P43-P50 semantic compatibility evidence into the P51 locked profile |

Full release verifier result, local current tags:

- command: `OOXML_FRESH_TAG_INSTALL=1 OOXML_OFFICE_GATE_JSON=<tmp>/ooxml-native-office-supported-valid-full-retry-180s.json uv run python scripts/verify_release_stack.py`
- result: `ooxml-spec` 269 passed; `ooxml-test-framework` 312 passed / 6 skipped; `ooxml-core` 1500 passed / 1 skipped; `ooxml-stubs` 68 passed; `python-pptx` 4885 passed / 6 skipped; `python-docx` 3560 passed / 5 skipped; schema 78 passed; compat smoke completed; Office repair dialogs 0; fresh install/import passed
- warning: `python-pptx` main worktree has unrelated local dirt in `playground/demo.potx`; verifier used detached HEAD worktree

P14 DOCX drawing release verifier closure, local current tags:

- command: `OOXML_DOCX_DRAWING_REGRESSION_JSON=<tmp>/p12-docx-drawing-regression-gate-office-ingest/docx-drawing-regression-summary.json OOXML_FRESH_TAG_INSTALL=1 OOXML_OFFICE_GATE_JSON=<tmp>/ooxml-native-office-supported-valid-full-retry-180s.json uv run python scripts/verify_release_stack.py`
- result: exit code 0; `ooxml-spec` 269 passed; `ooxml-test-framework` 336 passed / 6 skipped; `ooxml-core` 1519 passed / 1 skipped / 18 warnings; `ooxml-stubs` 68 passed; `python-pptx` 4894 passed / 6 skipped; `python-docx` 3563 passed / 5 skipped / 1 warning; schema 78 passed; compat smoke completed; Office repair dialogs 0; fresh install/import passed
- P13 gate line: `[PASS] docx drawing regression gate: selected_cases=60 represented_bucket_count=7 semantic_assertion_count=8 semantic_target_pass=60 semantic_target_fail=0 office_checked=True office_pass_total=60`
- boundary: this enforces measured P12 DOCX drawing regression evidence when supplied; it is not a full Word drawing parity or full Office compatibility claim

P15 zero-warning release verifier closure, local current tags:

- command: `OOXML_GENERATED_OUTPUT_GATE_JSON=<tmp>/ooxml-generated-output-gate/20260527T-generated-v1/generated-output-office-gate-final.json OOXML_NATIVE_CORPUS_DIR=<workspace>/ooxml-native-corpus OOXML_DOCX_DRAWING_REGRESSION_JSON=<tmp>/p12-docx-drawing-regression-gate-office-ingest/docx-drawing-regression-summary.json OOXML_FRESH_TAG_INSTALL=1 OOXML_OFFICE_GATE_JSON=<tmp>/ooxml-native-office-supported-valid-full-retry-180s.json uv run python scripts/verify_release_stack.py`
- captured output: `<tmp>/ooxml-p15-zero-warning-release-verifier-20260528T154500.txt`
- result: exit code 0; `[WARN]` line count 0; `[FAIL]` line count 0; generated-output active with `selected=504 docx=252 pptx=252 repair_dialogs=0`; stubs native preserve active for PPTX and DOCX; P13 DOCX drawing regression gate passed; Office repair dialogs 0; fresh install/import passed
- boundary: this proves a warning-free measured release verifier profile only; it is not a full Office compatibility or full Word drawing parity claim

P16 release profile freeze, local current tags:

- profile: `ooxml-stack/release-profiles/p15-zero-warning.json`
- command: `uv run python scripts/verify_release_profile.py --profile ../ooxml-stack/release-profiles/p15-zero-warning.json --summary-json <tmp>/ooxml-p16-release-profile-summary.json`
- summary JSON: `<tmp>/ooxml-p16-release-profile-summary.json`
- captured output: `<tmp>/ooxml-release-profile-20260528T101858Z.txt`
- result: `ok` true; `exit_code` 0; `warn_count` 0; `fail_count` 0; `generated_output_ok_count` 1; `docx_drawing_pass_count` 1; `stubs_preserve_ok_count` 2; `office_repair_zero_count` 1; `fresh_install_ok_count` 1
- boundary: this freezes the measured P15 zero-warning verifier profile; it is not a full Office compatibility or full Word drawing parity claim

P17 release evidence bundle freeze, local current tags:

- locked profile: `ooxml-stack/release-profiles/p16-zero-warning.locked.json`
- evidence directory: `ooxml-stack/release-evidence/p17/`
- manifest: `ooxml-stack/release-evidence/p17/manifest.json`
- command: `uv run python scripts/verify_release_profile.py --profile ../ooxml-stack/release-profiles/p16-zero-warning.locked.json --summary-json <tmp>/ooxml-p17-release-profile-summary.json`
- summary JSON: `<tmp>/ooxml-p17-release-profile-summary.json`
- result: `ok` true; `exit_code` 0; `warn_count` 0; `fail_count` 0; `generated_output_ok_count` 1; `docx_drawing_pass_count` 1; `stubs_preserve_ok_count` 2; `office_repair_zero_count` 1; `fresh_install_ok_count` 1; `hash_checked_count` 6; `size_checked_count` 6; `required_dir_count` 1
- boundary: this freezes and hash-validates the measured P16 evidence bundle; it is not a full Office compatibility or full Word drawing parity claim


P20 DOCX drawing coverage matrix, current evidence:

- evidence directory: `ooxml-stack/release-evidence/p20/`
- manifest: `ooxml-stack/release-evidence/p20/manifest.json`
- doc: phase doc pruned from current tree
- generator: `ooxml-test-framework` `943f966` / `v0.5.18`
- denominator: 190 DOCX/DOCM rows, 189 supported-valid DOCX/DOCM rows, 148 files with drawing signals, 100 selected P18/P19 regression cases
- family statuses: claimable measured for SmartArt, chart-in-drawing, floating anchors, group, textbox, and WordArt; regression-covered for canvas; preserve-only for inline drawing, picture, and mixed drawing cases
- P21 targets: raise canvas selected coverage, add targeted inline/picture active regression cases, and fill non-body story-part drawing gaps
- boundary: this refines the DOCX drawing claim boundary and does not increase the readiness score or claim full Word drawing parity

P19 DOCX drawing profile freeze, current evidence:

- locked profile: `ooxml-stack/release-profiles/p18-docx-drawing-coverage.locked.json`
- evidence directory: `ooxml-stack/release-evidence/p19/`
- manifest: `ooxml-stack/release-evidence/p19/manifest.json`
- command: `uv run python scripts/verify_release_profile.py --profile ../ooxml-stack/release-profiles/p18-docx-drawing-coverage.locked.json --summary-json <tmp>/ooxml-p19-docx-drawing-profile-summary.json`
- result target: `warn_count` 0, `fail_count` 0, `hash_checked_count` 6, `size_checked_count` 6, `required_dir_count` 1
- P18 DOCX drawing assertion: 100 selected cases, 7 represented buckets, semantic target pass 100/100, Office mutated-output pass 100/100
- current native Office assertion: 361 selected, 361 completed, 361 pass_total, repair/crash/macro/security blockers 0
- boundary: this freezes the measured P18 denominator; it is not a full Office compatibility or full Word drawing parity claim

P28 DOCX drawing profile freeze, current evidence:

- locked profile: `ooxml-stack/release-profiles/p28-docx-drawing-coverage.locked.json`
- evidence directory: `ooxml-stack/release-evidence/p28/`
- manifest: `ooxml-stack/release-evidence/p28/manifest.json`
- command: `uv run python scripts/verify_release_profile.py --profile ../ooxml-stack/release-profiles/p28-docx-drawing-coverage.locked.json --summary-json <tmp>/ooxml-p28-post-review-profile-summary.json --output <tmp>/ooxml-p28-post-review-profile-output.txt`
- post-review result: `ok` true; `exit_code` 0; `warn_count` 0; `fail_count` 0; `hash_checked_count` 6; `size_checked_count` 6; `required_dir_count` 1; `fresh_install_ok_count` 1
- P21 DOCX drawing assertion: 130 selected cases, 10 represented buckets, 11 semantic assertions, semantic target pass 130/130, Office mutated-output pass 130/130
- P23 native Office assertion: 361 selected, 361 completed, 361 pass_total, 360 pass, 1 pass_with_dialog, repair/crash/macro/security blockers 0
- boundary: this freezes the measured P21/P23 denominator; it is not a full Office compatibility or full Word drawing parity claim

P33 DOCX drawing active-editing v1, current evidence:

- claim: `100% compatibility under the P33 measured DOCX drawing active-editing v1 denominator.`
- code: `python-docx` `3371128` post-review handle targeting fix, originally `8fdb3cd`; `ooxml-test-framework` `dfaccfd`
- docs/evidence: phase doc pruned from current tree; `release-evidence/p33/manifest.json`; static dashboard `release-evidence/p33/dashboard/index.html`
- result: 130/130 locate+classify, 10/10 families, 130/130 edit/control outcomes, 118/118 semantic active edits, 12/12 preserve controls, 130/130 library open-save, 130/130 package invariant, 130/130 Desktop Word open
- blockers: repair/security/crash/macro/relationship loss/missing parts/binary mutation/silent no-op/public overclaim all 0
- boundary: this is active editing compatibility only under the fixed P33 denominator; it is not a full Office compatibility or full Word drawing parity claim

P35 stable-handle active-editing gate, current evidence:

- claim: `100% stable-handle targeting under the P35 measured DOCX drawing active-editing handle denominator.`
- code: `python-docx` `b406981`; `ooxml-test-framework` `ee6e42e`
- evidence: phase doc pruned from current tree; `release-evidence/p35/manifest.json`
- result: 130/130 target handle edit pass, 976 same-operation sibling comparisons, 0 wrong-handle mutations, 130/130 Desktop Word open pass, 0 repair/security/crash/macro/timeout blockers
- boundary: this is stable-handle targeting under the selected P35 denominator; it is not full Office compatibility or full Word drawing parity

P18 DOCX drawing coverage expansion, local current evidence:

- doc: phase doc pruned from current tree
- native corpus commit: `abb503b`
- test framework commit: `ed3e1b0`
- no-Office summary JSON: `<tmp>/p18-docx-drawing-regression-gate-no-office/docx-drawing-regression-summary.json`
- Office-ingest summary JSON: `<tmp>/p18-docx-drawing-regression-gate-office-ingest/docx-drawing-regression-summary.json`
- Desktop Word evidence JSON: `<tmp>/p18-docx-drawing-office-gate.json`
- result: 370 native corpus rows; 190 DOCX/DOCM; SmartArt files 2 -> 8; drawing canvas files 1 -> 10; selected cases 60 -> 100; semantic target pass 100/100; library open/save 100/100; package invariants 100/100; Desktop Word 100/100 pass; repair/crash/security/macro blocker counts 0
- boundary: this expands the measured DOCX drawing denominator; it is not a full Word drawing parity or full Office compatibility claim

Real Office non-macro smoke result, local 2-file sample:

- command: `uv run python tools/office-open-gate/office_open_gate.py <pptx> <docx> --timeout-seconds 60 --dialog-wait-seconds 10 -o <tmp>/ooxml-office-open-nonmacro-smoke-v12.json`
- result: 2 total, 2 pass, repair_dialog_count 0, gate_pass true

Real Office native supported-valid smoke result, local 5-file sample:

- command: `python3 tools/office-open-gate/native_corpus_office_gate.py <workspace>/ooxml-native-corpus/manifests/corpus.csv --limit 5 --timeout-seconds 75 --dialog-wait-seconds 10 -o <tmp>/ooxml-native-office-supported-valid-smoke-v2.json`
- denominator: 5 selected from 341 supported-valid non-macro files; excluded 1 quarantine and 8 macro-enabled files
- result: 5 total, 5 pass, repair_dialog_count 0, office_crash_count 0,
  macro_security_dialog_count 0, macro_timeout_count 0, gate_pass true

Real Office native supported-valid full result, local 341-file gate:

- command: `python3 tools/office-open-gate/native_corpus_office_gate.py <workspace>/ooxml-native-corpus/manifests/corpus.csv --timeout-seconds 180 --dialog-wait-seconds 15 --resume --retry-non-pass -o <tmp>/ooxml-native-office-supported-valid-full-retry-180s.json`
- denominator: 341 supported-valid non-macro files; excluded 1 quarantine and
  8 macro-enabled files
- result: 341 total, 341 completed, 340 pass, 1 pass_with_dialog,
  repair_dialog_count 0, office_crash_count 0, macro_security_dialog_count 0,
  macro_timeout_count 0, gate_pass true
- benign dialog: `docx_ms_expansion_181_alt-chunk-header.docx` showed a Word
  field-update prompt; no repair dialog was detected

Real Office macro diagnostic, local 8-file native macro subset:

- command: `uv run python tools/office-open-gate/office_open_gate.py <4 pptm> <4 docm> --timeout-seconds 60 --dialog-wait-seconds 10 -o <tmp>/ooxml-office-open-macro-all-v16.json`
- result: 8 total, 8 macro_security_dialog, repair_dialog_count 0,
  office_crash_count 0, macro_timeout_count 0, gate_pass false
- interpretation: macro/security prompts are now machine-classified instead of
  requiring manual clicks, but they remain blocking for full release-corpus
  Office gate evidence.

Native corpus inspection after quarantine:

- command: `python3 scripts/inspect_corpus.py`
- result: 370 total, 369 passed, 0 failed, 0 skipped, 1 quarantined,
  370 hash-verified Office files
- quarantine: `docx_media_dense_case` because Word reports unreadable content

Render smoke result, local 2-file sample:

- command: `uv run ooxml-render-smoke <docx> <pptx>`
- result: 2 total, 2 pass, gate_pass true


P40 DOCX drawing active-editing v2 freeze, current evidence:

- claim: `100% compatibility under the P40 measured DOCX drawing active-editing v2 public-operation-row denominator.`
- code tags: `ooxml-test-framework` `4c304fd` / `v0.5.21`; `ooxml-core` `96adcd2` / `v0.3.39`; `ooxml-stubs` `bc6ae02` / `v0.2.12`; `python-docx` `9f252a6` / `v1.2.8`; `python-pptx` `83817ce8` / `v2.0.9`
- docs/evidence: phase doc pruned from current tree; `release-profiles/p40-docx-drawing-active-editing-v2.locked.json`; `release-evidence/p40/manifest.json`
- result: 260/260 public-operation rows pass over 130 unique `input_file|stable_id` handles, 10/10 drawing families, 20 public operation labels, 10 semantic base operations, 0 new unique handles, 260/260 public API locate/edit, 260/260 semantic hit, 1952 same-operation sibling checks unchanged, 260/260 Desktop Word open pass
- blockers: repair/security/crash/macro/relationship loss/missing parts/binary mutation/silent no-op/public overclaim all 0
- boundary: this is active editing compatibility only under the fixed P40 measured public-operation-row denominator; it is not a full Office compatibility, full Word drawing parity, larger unique-handle denominator, or 20-independent-mutator claim

P41 DOCX drawing active-editing v2 owner dashboard, current evidence:

- claim: `100% inspectable owner dashboard under the P40 measured DOCX drawing active-editing v2 public-operation-row denominator.`
- generator: `ooxml-test-framework` `4c304fd` / `v0.5.21`
- docs/evidence: phase doc pruned from current tree; `release-evidence/p41/manifest.json`; `release-evidence/p41/dashboard/index.html`
- result: 260/260 public-operation rows rendered, 130 unique handles rendered, 10/10 semantic base operations, 20/20 public operation labels, 130 P35-base rows, 130 P38-variant alias rows, 0 new unique handles, 260/260 semantic pass rendered, 260/260 Desktop Word open pass rendered, 1952 same-operation sibling checks unchanged
- blockers: wrong-handle mutation, repair/security/crash/macro, relationship loss, missing parts, binary mutation, silent no-op, and public overclaim all 0
- boundary: this adds inspectable owner evidence for P40; no full Office compatibility claim, no full Word drawing parity claim, no SmartArt editor parity claim, no pixel/layout/cache parity claim, and no Office layout/cache recomputation parity claim

P42 DOCX drawing active-editing v3 real expansion, current evidence:

- claim: `100% compatibility under the P42 measured DOCX drawing active-editing v3 real-expansion denominator.`
- code tags: `ooxml-test-framework` `2abb25d` / `v0.5.23`; `ooxml-core` `30fcb48` / `v0.3.40`; `ooxml-stubs` `f3afee8` / `v0.2.13`; `python-docx` `1337a80` / `v1.2.9`
- post-review hardening: `ooxml-test-framework` `d63f199` fails denominator observation errors; `ooxml-core` `7edb8be` redacts release profile command paths and locks `observation_error_count`
- docs/evidence: phase doc pruned from current tree; `release-evidence/p42/manifest.json`; `release-evidence/p42/release-profile-summary.json`; `release-profiles/p42-docx-drawing-active-editing-v3.locked.json`
- result: 208/208 unique `input_file|stable_id` handles pass, 130 P35 base handles preserved, 78 new unique handles added, 13 independent semantic operations, 13 public operation labels, 10/10 drawing families, 208/208 public API locate/edit, 208/208 semantic hit, 1920 same-operation sibling checks unchanged, 208/208 Desktop Word open pass, denominator observation errors 0
- blockers: wrong-handle mutation, repair/security/crash/macro/timeout, relationship loss, missing parts, binary mutation, silent no-op, alias-row expansion, and public overclaim all 0
- boundary: this is active editing compatibility only under the fixed P42 measured real-expansion denominator; no full Office compatibility claim, no full Word drawing parity claim, no SmartArt editor parity claim, no pixel/layout/cache parity claim, and no Office layout/cache recomputation parity claim

P51 OOXML measured candidate semantic inventory freeze, current evidence:

- claim: `100% classified object-candidate semantic inventory under the P51 measured OOXML Semantic Compatibility 1.0 denominator.`
- code tags: `ooxml-test-framework` `a760e70` / `v0.5.25`; `ooxml-core` `1fd3be4` / `v0.3.42`
- docs/evidence: phase doc pruned from current tree; `release-profiles/p51-ooxml-semantic-compatibility-1.locked.json`; `release-evidence/p51/manifest.json`; dashboard `release-evidence/p49/dashboard/index.html`
- denominator: 361 selected supported-valid packages, 90,864 XML parts, 90,864 XML parse pass, 0 XML parse failures, 108,535 package parts, 112,082 relationships, 0 unclassified relationship targets, 1,682 distinct QNames, 43,163,913 element instances, 1,488,628 semantic object candidates, 32 families
- status counts: 0 active-editable in the global P43 inventory, 1,192,484 inspectable, 296,144 preserve-only, 0 classifier-emitted unsupported rows; P42 remains the separate active-editing denominator with 208/208 handles passing
- replay result: `ok=true`, `warn_count=0`, `fail_count=0`, `hash_checked_count=31`, `size_checked_count=31`, `fresh_install_ok_count=1`, P43-P50 gates all pass, public overclaim count 0
- blockers: unclassified objects, allowed-status violations, relationship loss, missing parts, unintended binary/media mutation, unsupported silent no-op, Office repair/security/crash/macro blockers, and public overclaims all 0
- boundary: this is measured object-candidate classification over the current supported-valid corpus plus prior measured active-edit evidence; candidate rows are not every XML element instance, and `unsupported=0` means the current classifier emitted no unsupported rows. No full Office compatibility claim, no full ECMA-376 universe coverage claim, no full format parity claim, no SmartArt editor parity claim, and no renderer/layout/cache recomputation parity claim

P60 DOCX/PPTX semantic understanding 1.0 freeze, current evidence:

- claim: `100% semantic understanding under the P60 measured DOCX/PPTX object-candidate understanding v1 denominator, with a bounded semantic-editing v1 launch contract.`
- code tags: `ooxml-test-framework` `25fc243` / `v0.5.27`; `ooxml-core` `1769422` / `v0.3.43`
- docs/evidence: phase docs pruned from current tree; `release-profiles/p60-docx-pptx-semantic-understanding-1.locked.json`; `release-evidence/p60/manifest.json`; dashboard `release-evidence/p59/dashboard/index.html`
- denominator: 361 selected supported-valid packages, 185 DOCX packages, 176 PPTX packages, 1,488,628 object candidates, 361,745 DOCX object candidates, 1,126,883 PPTX object candidates, 39 family-format cells
- understanding result: P52/P53/P54/P55/P56/P57/P58/P59 gates all pass, 1,488,628/1,488,628 semantic understanding rows pass, 1,488,628/1,488,628 rows reach U2-or-higher, unexplained required-field missing 0, owner decision missing 0, dependency decision missing 0, XML parse failures 0
- editing launch result: P42 active editing preserved, 208/208 active-proven rows, 10 semantic editing launch families, 20 representative launch operation rows, contract-only active rows 0, wrong-handle mutation 0
- blockers: repair/security/crash/macro timeout, relationship target unclassified, missing required parts, unsafe edit silent no-op, preserve-only mutation allowed, unsupported mutation allowed, public overclaim, and edit contract overclaim all 0
- boundary: this is measured DOCX/PPTX object-candidate understanding plus a bounded DOCX drawing active-edit preservation contract. No full OOXML claim, no full Office compatibility claim, no full ECMA-376 universe coverage claim, no full Word/PPTX parity claim, no universal editing claim, no SmartArt editor parity claim, and no renderer/layout/pixel/cache recomputation parity claim

## Remaining Blockers

No blocker remains for the documented 98/100 readiness target. Remaining items
are classified exclusions or future scope, not supported-valid release blockers.

## Classified Exclusions

- `docx_media_dense_case.docx`: quarantined because desktop Word reports
  unreadable content. This is excluded from the supported-valid release corpus.
- 8 macro-enabled files: excluded from the supported-valid non-macro Office
  gate and tracked separately. The current macro diagnostic reports 8/8
  `macro_security_dialog`, with 0 repair dialogs, 0 crashes, and 0 macro
  timeouts.

## Reproduction Commands

```bash
cd <workspace>/ooxml-test-framework
uv run pytest
python3 tools/compat-test/classify_open_failures.py \
  tools/compat-test/results/runs/p9-strict-ns-equivalence-20260525T120000Z/results_docx.json \
  tools/compat-test/results/runs/p9-strict-ns-equivalence-20260525T120000Z/results_pptx.json \
  --path-root <compat-corpus-root> \
  -o tools/compat-test/open-failure-classification-current-head.json
```

```bash
cd <workspace>/ooxml-core
uv run pytest
OOXML_FRESH_TAG_INSTALL=1 \
OOXML_OFFICE_GATE_JSON=<tmp>/ooxml-native-office-supported-valid-full-retry-180s.json \
uv run python scripts/verify_release_stack.py
```

```bash
cd <workspace>/ooxml-native-corpus
python3 scripts/corpus_manifest.py validate
python3 scripts/corpus_manifest.py validate --archive-dir dist/native-corpus
python3 scripts/corpus_bundle.py verify --tier all
python3 scripts/corpus_manifest.py coverage
python3 scripts/corpus_readiness.py --target 370
python3 scripts/inspect_corpus.py
python3 scripts/corpus_drift.py
python3 -m unittest discover -s tests -q
```

## Claim Boundary

Allowed claim today: **>=98/100 release readiness under this documented rubric;
100% open and active roundtrip for supported-valid files in the measured broad
corpus, with exact and compatible preserve reported separately; 0 desktop Office
repair dialogs across the supported-valid non-macro native corpus gate.**

Not allowed today: **100% Office compatible**, **all macro-enabled files as
ordinary pass cases**, or **invalid/corrupt/encrypted files as supported-valid
failures**.

## P70 Preserve-Only Zero Freeze

- P70 PASS as preserve-only accounting closure under the measured P61-P68 DOCX/PPTX denominator.
- baseline_preserve_only_status_count: 296144
- final_preserve_only_status_count: 0
- promoted_from_preserve_only_count: 296144
- object_level_active_editable_count_at_p70: 11456
- aggregate_package_level_covered_count_at_p70: 284688
- unknown_extension_object_count: 0
- unclassified_object_count: 0
- unsupported_object_count: 0
- DOCX preserve-only: 0
- PPTX preserve-only: 0
- semantic/surface hit accounting: 296144/296144
- Desktop Word open pass rows: 20147
- Desktop PowerPoint open pass rows: 275997
- generic replay package open pass: 359/359
- repair/security/crash blockers: 0/0/0
- public_claim_beyond_measured_cells: 0

Boundary: P70 proves preserve-only accounting closure with row-level P63/P64 evidence plus aggregate P67/P68 package-level replay evidence. It does not prove that all 296144 former preserve-only objects are object-level active-editable. P71-P80 is required to materialize per-object rows, handles, diffs, and object-bound Office evidence for the 284688 aggregate replay-covered rows. P70 also does not prove renderer/pixel/layout parity, macro support, encrypted package support, or arbitrary vendor-private semantic interior parity beyond the measured active operations.

## P80 Former Preserve-Only Object-Level Active Editability Freeze

- P80 PASS as object-level active editability under the measured former preserve-only DOCX/PPTX denominator.
- baseline_former_preserve_only_count: 296144
- former_preserve_only_object_row_count: 296144
- object_level_active_editable_count: 296144
- object_level_active_editable_rate: 100
- surface_editable_count: 296144
- semantic_editable_count: 0
- aggregate_ledger_row_count: 0
- aggregate_replay_counted_as_object_level_count: 0
- package_level_oracle_counted_as_object_level_count: 0
- status_only_promotion_count: 0
- label_only_promotion_count: 0
- policy_only_promotion_count: 0
- raw_xml_escape_hatch_required_count: 0
- stable_handle_assigned_count: 296144
- selector_resolve_failure_count: 0
- selector_multi_match_count: 0
- target_digest_changed_count: 296144
- sibling_unexpected_mutation_count: 0
- wrong_handle_mutation_count: 0
- object_office_bound_pass_count: 296144
- object_office_bound_fail_count: 0
- public_api_edit_pass_count: 296144
- typed_error_contract_pass: true
- public_claim_beyond_measured_cells: 0
- fresh install/import from tags: pass

Boundary: P80 proves every former preserve-only object row has object-level handle, selector, digest, Office-bound, and public API surface-edit evidence. It does not claim semantic interior editing for all objects; the entire former preserve-only denominator remains `surface-editable`, with `semantic_editable_count = 0`. It also does not prove full Office compatibility, full OOXML semantics, renderer/pixel/layout/cache parity, macro support, encrypted package support, or arbitrary vendor-private semantic parity.
