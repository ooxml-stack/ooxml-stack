# Local integration verification, 2026-09-26

> Historical record: results and commands describe the recorded revision.
> Follow [current artifact storage](ARTIFACT-STORAGE.md) for external evidence
> and the [documentation index](README.md) for current entry points.

The pinned runner remains `9da7a24e240a3f2b086c2383a164d29216330ed7` for the engine run. This change only corrects the mutation-probe fixture and current-registry budget verification; it does not change runner execution or rewrite historical release evidence.

The ChartEx ordering probe previously wrote `pt@val`. The current owner reads the actual ChartEx string-point text, so both probe variants measured empty values. The replacement uses text content and proves that leaf-first passes while root-first is detected. All 13 mutation cases and all 12 distinct target rules remain required.

The budget tests formerly compared today's expanded rule registry to historical counts and bytes from P98. This incorrectly treated newly registered rules as lost coverage. They now compare before/after proof sets over the same current registry, requiring all P98 additions to be present and newly covered. `tests/fixtures/current-coverage-budget.json` records the new denominator: 86 uncovered format-rule pairs (DOCX 36, PPTX 33, XLSX 17). These are unproven by the two historical mutation campaigns, not 86 known editing defects. The historical 69-pair snapshot remains unchanged under `release-evidence/p98/`.

Local validation: runner/inventory suite initially 463 passed with 15 environment failures; after supplying declared parser dependencies and integrated owner imports, 5 genuine stale-probe/baseline failures remained. The corrected 20-test mutation/budget selection passes. No remote CI, push, release or native Office compatibility claim is made here.
