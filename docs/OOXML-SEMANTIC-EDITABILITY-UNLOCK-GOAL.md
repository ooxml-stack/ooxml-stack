# OOXML Semantic Editability Unlock Goal

This is the current strategy for moving from measured semantic editability
toward broader OOXML compatibility. It is a strategy page, not a replay prompt.

## Current State

Source of truth:

- `docs/OOXML-ELEMENT-CAPABILITY-LEDGER.md`
- `release-evidence/former-preserve-only-semantic-editability/promotion-summary.json`
- `release-evidence/former-preserve-only-semantic-editability/remaining-bucket-summary.json`
- `release-evidence/former-preserve-only-semantic-editability/unlock-blocker-taxonomy.json`
- `release-evidence/former-preserve-only-semantic-editability/target-queue-summary.json`

Current strict numbers:

- surface-editable denominator: `296,144`
- semantic-editable rows: `272,894`
- semantic blockers remaining: `23,250`
- promotion rows with API/CLI/MCP/native Office proof: `20,151`
- full claim proven: `false`

Remaining blocker buckets:

| Reason | Rows | Treatment |
| --- | ---: | --- |
| `semantic_value_available_pending_proof` | 14,189 | Promote only after exact row proof and Office pass. |
| `relationship_identity_like` | 2,989 | Keep blocked until a relationship-safe operation exists. |
| `binary_payload_reference` | 2,975 | Needs relationship and payload oracle before mutation. |
| `needs_family_model` | 2,657 | Implement one family model at a time. |
| `needs_vendor_family_model` | 440 | Keep vendor-private until an explicit vendor contract exists. |

## Objective

Make every remaining row explainable and move rows only when the explanation is
backed by a policy, model, or oracle change.

Allowed outcomes:

- promoted with full row-level proof
- blocked by confirmed native Office boundary
- blocked by identity, relationship, or binary-payload risk
- blocked by missing family model
- explicitly unsupported under the current public claim boundary

## Non-Goals

Do not claim:

- full OOXML compatibility
- full Office compatibility
- all XML elements editable
- all object candidates editable
- package-level Office pass as object-level semantic pass
- marker-only or surface-only edits as semantic editability

Do not treat `close_error`, `repair_dialog`, `unreadable_content`,
`pass_with_dialog`, security dialog, crash, or timeout rows as promotion rows.

## Hard Promotion Rules

A row is semantic-editable only if all gates pass:

- public API path
- CLI path
- real MCP `list_tools` and `call_tool` path
- target object changed
- exact requested after-value is present
- same-operation siblings unchanged
- package invariant pass
- native Word or PowerPoint opens without repair/security/crash
- hard audit pass after Office evidence exists

Boundary rows stay visible in dashboards, but never merge into
`promotion-rows.jsonl`.

## Current Workstreams

1. Refresh current ledgers before acting:
   `make campaign-unlock-plan && make dashboard-md OUT=docs/OOXML-ELEMENT-CAPABILITY-LEDGER.md`.

2. Take low-risk proof batches first:
   use `targeted-unlock-replay-plan.json` only when it contains non-boundary
   quick-proof rows.

3. Treat Office boundaries as product diagnostics, not burn-down targets:
   confirmed close/error and unreadable-content packages need minimal
   reproduction and root-cause classification before more replay.

4. Implement one family model at a time:
   start only when the family has a clear before-value extractor, after-value
   oracle, sibling-unchanged oracle, and Office gate expectation.

5. Keep the public claim boundary current:
   update the capability ledger and closeout notes before making any broader
   compatibility statement.

## Next Decision

Use the refreshed target queue to choose between:

- quick proof replay for already-safe hydrated rows
- one schema policy unlock with tests
- one family model implementation with explicit oracle
- one Office boundary diagnostic for a high-impact damaged package
