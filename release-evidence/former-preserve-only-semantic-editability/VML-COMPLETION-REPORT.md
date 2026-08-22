# VML Completion Report

## Result

The measured `vml_drawing` family is closed under the completion contract.
The durable row inventory contains 3,314 unique rows:

| Final state | Rows |
| --- | ---: |
| promoted semantic-editable | 2,298 |
| identity or reference | 634 |
| structurally coupled | 137 |
| no semantic value | 103 |
| Office boundary | 87 |
| terminal unsupported | 55 |
| total | 3,314 |

`2,298 + 1,016 = 3,314`. There are zero
`ready_for_canary`, `needs_operation`, `needs_spec_resolution`,
`pending_proof`, or `unresolved` rows in the final VML completion inventory.

Authoritative evidence:

- `VML-COMPLETION-INVENTORY.jsonl`: every measured row, its current value
  snapshot, schema snapshot, operation, latest Office classification, terminal
  reason, and evidence paths.
- `VML-COMPLETION-INVENTORY-SUMMARY.json`: 3,314 rows, 3,314 unique rows,
  invariant pass.
- `promotion-rows.jsonl`: row-level API, CLI, real MCP, exact oracle,
  sibling-isolation, package-invariant, and native Office results.

## Run bounds

| Field | Value |
| --- | --- |
| start UTC | 2026-08-03T16:31:23Z |
| completion audit UTC | 2026-08-04T05:16:03Z |
| start stack commit | `db7e955e` |
| final evidence commit | `be3ed77c` |
| engine dependencies | `ce65930`, `de1c85c` |
| start global semantic / blocker | 274,756 / 21,388 |
| final global semantic / blocker | 275,210 / 20,934 |
| start VML promoted | 1,814 |
| final VML promoted / terminal | 2,298 / 1,016 |

## Promoted rows

The final inventory maps promoted rows as follows. The 1,122 rows without a
campaign operation are semantic-editable rows inherited from the measured
baseline; the remaining rows have typed campaign operations.

| Operation | Inventory rows |
| --- | ---: |
| measured baseline operation | 1,122 |
| `vml.formula.eqn.set_value` | 370 |
| `vml.image.metadata.set_title` | 276 |
| `vml.path.metadata.set_value` | 196 |
| `vml.stroke.set_join_style` | 125 |
| `vml.fill.set_enabled` | 100 |
| `vml.shape.text.set` | 78 |
| `vml.shape.stroke.set_color` | 14 |
| `vml.stroke.set_enabled` | 9 |
| `vml.shape.fill.set_color` | 4 |
| `vml.shadow.set_enabled` | 3 |
| `vml.textpath.set_enabled` | 1 |

The campaign hard audit covers 1,145 VML promotion evidence rows. Its exact
row count is 1,145, `failures == {}`, and `audit_pass == true`. The final
operation-specific audits are also clean: image title 276/276, path 196/196,
shadow boolean 3/3, and text-path boolean 1/1.

## Terminal rows

All 1,016 non-promoted rows have a non-empty terminal reason and at least one
durable evidence path. Their terminal class totals are shown in the result
table. The row inventory preserves the exact per-row reason; the largest
reason groups are identity IDs/references, empty fill/stroke/path containers,
shape-type coordinates, textbox inset geometry, and native Office boundaries.

The 87 Office-boundary rows preserve the latest status rather than accepting
an older pass:

| Latest native Office status | Rows |
| --- | ---: |
| timeout | 36 |
| close error | 29 |
| unreadable content | 16 |
| pass with dialog | 6 |

These rows were not retried after terminal classification and are not counted
as semantic-editable.

## Atomic commits

Stack commits owned by this completion run, in order:

```text
11d85e9b 09e94b2e 227c5e02 48385ec8 d0d42145 46274ad3 918bad9a
bcae6222 4b792648 f6f2f433 d43e0e40 8e3c1df1 d477bb6e a5c1d1c8
bd7e4d42 29f8ff9d 1958e187 1819b500 5bdcf0a9 cd3626b7 742c7cc8
d0d2c1af 5c89ab2e f786a689 35e3747a 85944e18 1decb52f 20cecb5f
44e55d49 a9a6ff3e 2f02f8bb b5defc17 b2e4383a 64c1002c 84625d19
71df7b7c 46bc6bd7 31a16b33 21495af4 be3ed77c
```

Engine commits owned by the run:

```text
ce65930 de1c85c
```

Interleaved xlsx commits were unrelated and are excluded from this list.

## Final gates

- Stack full suite: 332 passed, 0 failed, 0 skipped
  (`/tmp/ooxml-vml-stack-final.xml`, 2026-08-04).
- Engine full suite: 2,612 passed, 4 skipped, 0 failed
  (`/tmp/ooxml-vml-engine-boolean-final.xml`, 2026-08-04).
- Campaign unlock plan, chunk plan, Markdown dashboard, and HTML dashboard:
  regenerated after the final promotion.
- Final inventory invariant: pass.
- Hard audit failures: none.
- Native Office repair/unreadable failures among promoted rows: none.
- No push was performed. The stack branch remained local and ahead of its
  upstream.
- The Goal Markdown and the run checkpoint were not committed.

This report and the durable inventory are sufficient to reproduce the VML
completion claim without the Goal file.
