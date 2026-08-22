# Compatibility Contract 98 Readiness Closeout

Date: 2026-07-30
Branch: `compatibility-contract-98-readiness`
Evidence head: `34b58d4`

## PR Description

This branch closes the measured compatibility-contract 98 readiness evidence gap
for the former-preserve-only semantic editability campaign.

Key changes:

- Extends semantic value policies for selected OMML on/off values and Word 2010
  `w14` numbering metadata values.
- Adds the final promoted semantic editability evidence bundle under
  `release-evidence/former-preserve-only-semantic-editability/`.
- Documents the large evidence workflow so mutable aggregate ledgers are
  regenerated or squashed before push, instead of pushing repeated intermediate
  `promotion-rows.jsonl` snapshots.

Measured result:

- Promotion rows: `20,151`
- Reference target rows: `20,079`
- Over target: `72`
- Local adjusted gap: `-72`
- API, CLI, MCP, and native Office path checks for promoted rows: `20,151`
  each.

Validation:

- `python3 -m pytest tests` -> `211 passed`
- `make evidence-hygiene` -> pass
- `make repo-hygiene` -> pass
- `git lfs status` -> clean

Boundaries:

- This proves the measured semantic editability campaign target under the
  documented denominator. It does not prove full OOXML compatibility, full
  Office compatibility, or global full-write support.
- Office boundary rows such as `close_error`, `unreadable_content`,
  `pass_with_dialog`, and `timeout` remain boundary evidence only and are not
  counted as promotion passes.
- Damaged or repair-dialog PPTX cases, including `pptx_chart_dense_203slides`,
  are excluded from the promoted pass count.
- Current HEAD hygiene is public-safe under the local audit, but full Git
  history remains not public-safe because older reachable blobs still contain
  path and large-blob debt.

## Readiness Summary

| Metric | Value |
| --- | ---: |
| Promotion row count | 20,151 |
| Reference target rows | 20,079 |
| Rows over target | 72 |
| Local adjusted gap | -72 |
| Former preserve-only denominator | 296,144 |
| Semantic editable count | 270,143 |
| Semantic editable remaining | 26,001 |
| Aggregate gap row count | 0 |
| CLI unchecked promoted rows | 0 |
| MCP unchecked promoted rows | 0 |
| Office blocker count | 0 |
| Full semantic claim proven | false |

Evidence files:

- `release-evidence/former-preserve-only-semantic-editability/promotion-summary.json`
- `release-evidence/former-preserve-only-semantic-editability/promotion-rows.jsonl`
- `release-evidence/former-preserve-only-semantic-editability/chunk-boundary-summary.json`
- `release-evidence/former-preserve-only-semantic-editability/office-results/`
- `release-evidence/former-preserve-only-semantic-editability/public-paths/`
- `release-evidence/former-preserve-only-semantic-editability/staged-rows/`

Boundary summary:

| Boundary type | Count |
| --- | ---: |
| Office boundary records | 160 |
| Public API failed records | 5 |
| Timeout records | 1 |
| Total boundary records | 166 |
| Boundary packages | 96 |

Native Office boundary statuses:

| Office status | Count |
| --- | ---: |
| `close_error` | 145 |
| `unreadable_content` | 11 |
| `pass` boundary records | 4 |
| missing Office status | 3 |
| `pass_with_dialog` | 2 |
| `timeout` | 1 |

Hygiene summary:

| Check | Value |
| --- | ---: |
| Current user path hits | 0 |
| Current raw release-evidence user path hits | 0 |
| Current normal Git blobs over 10MB | 0 |
| Files that should be LFS but are not | 0 |
| LFS status clean | true |
| Current worktree public-safe | true |
| Full history public-safe | false |
| Historical user-path blobs | 59 |
| Historical secret-like blobs | 0 |
| Historical blobs over 10MB | 540 |
| Historical blobs over 50MB | 91 |
| Historical blobs over 100MB | 1 |

Recommended public-release posture:

- Use the current branch for review of this readiness evidence.
- Do not claim full-history public safety from this branch.
- Use a fresh public mirror if the repository needs public-safe history.
