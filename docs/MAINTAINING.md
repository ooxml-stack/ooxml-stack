# Maintainer guide

This guide covers Stack's shared tooling. For runtime or application behavior,
start with the [repository ownership map](ARCHITECTURE.md).

## Workspace and inputs

Use [developer worktrees](DEVELOPER-WORKTREES.md) for a recorded task checkout.
Keep generated outputs in the external [artifact store](ARTIFACT-STORAGE.md).
Only populate private sibling repositories when authorized and required by the
selected check; a public clone does not grant access to them.

The dependency policy and generated plan have different roles:

- `ci/ecosystem-policy.json` declares nodes, required inputs and verification
  bindings. Its metadata is not a live GitHub access-status query.
- `ci/ecosystem-plan.json` is a derived baseline consumed by checks. Editing
  documentation does not refresh it or prove that current checkouts match it.
- Inventory scans record observations about a particular environment. Treat
  missing inputs, stale source identities and mismatches as such.

For an intentional plan update, use the inventory's existing default-branch
basis workflow; see [the specification](ECOSYSTEM-INVENTORY-SPEC.md). Review the
resulting input identities and diagnostics. Do not hand-edit generated plan
bytes or change a consumer's runner pin to suppress a mismatch.

## Verification entry points

Run project tests on the designated test host/environment. Local link, Git and
file checks suffice for documentation-only changes under the shared workspace
rules. Record the tested identity, environment, scope and original outcomes.

| Scope | Entry point | Environment |
| --- | --- | --- |
| Pinned inventory/test dependencies | `make ecosystem-inventory-deps` | Python 3.12 and package access |
| Shared runner, worktree and workspace regressions | `make runner-test` | Pinned test dependencies; runner tests do not start Docker |
| Dependency inventory regressions | `make ecosystem-inventory-test` | Pinned parser/test dependencies |
| Generated evidence placement | `make evidence-hygiene` | Python standard library |
| Mutation and coverage tooling | Relevant `tests/test_p97_*.py` and `tests/test_p98_*.py` | Declared format/validation dependencies; native checks have additional requirements |

The workflow files in [`.github/workflows`](../.github/workflows/) are the
execution definitions. A local command result does not establish that a remote
workflow ran. Report blocked checks separately rather than marking them passed.

Shared-runner `describe`, `run` and `verify-report` have distinct meanings; see
[the runner specification](ECOSYSTEM-RUNNER-SPEC.md). Describing a request does
not execute a gate. Model evaluations are separate and require an authorized
plan and budget.

## Documentation and publication

Keep the [documentation index](README.md) current. Product-facing instructions
belong in the overview and architecture; tool contracts belong in their owning
specifications. Historical records keep original identities and are labeled as
history, not reused as current installation or readiness instructions.

Follow the [public content policy](../VISIBILITY.md). In particular, an
untracked/ignored file, an LFS classification or a passing path-hygiene check is
not a publication license or a complete disclosure review. The historical
public-mirror proposal is not an automatic export procedure.

## Change handoff

Record the changed behavior or documentation scope, validation performed,
unresolved findings, evidence location and checkout disposition. Preserve source
identities, immutable fixtures and original run results. Changes to shared
entry points require review of downstream callers; moving a script just to
reorganize directories can break pinned consumers.
