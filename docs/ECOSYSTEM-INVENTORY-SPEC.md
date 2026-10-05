# Ecosystem inventory specification: implementation baseline

This specification defines the committed `ci/ecosystem-plan.json`, the ignored
`ci/reports/scan.json`, and their derivation rules. Section 0 records the design
changes incorporated into the implementation. Historical observations in §9
are tied to their original run; they are not current diagnostic counts.
The inventory does not modify another repository's CI, dependencies or hooks.

## 0. Design changes incorporated into the baseline

| # | Contract | Section |
| --- | --- | --- |
| 1 | Group all actual dependencies by `(upstream, role)` for `version_skew`; policy declares uniformity requirements and exceptions, not which groups to inspect. | §7 |
| 2 | Record a corpus release tag and its source separately from the configured Git commit; do not assume equivalence. | §6 |
| 3 | Include Apps in nodes and test impact, retain its runtime dependency on Engine, and let policy control release participation. | §8 |
| 4 | The plan is a deterministic function of selected paths and file bytes, including uncommitted changes. | §2.1 |
| 5 | Use stable policy keys for nodes; actual remotes, common directories and checkouts belong in scan observations. | §3 |
| 6 | Detect a moved tag only when an expected commit has been recorded; a tag-only declaration establishes its current target. | §4.3 |
| 7 | Missing explicitly required input is `missing_input`, never an optional omission. | §9 |
| 8 | Report `source_override_conflict` for conflicting source declarations; `uv.sources` selectors take precedence over direct dependency selectors. | §4, §9 |
| 9 | Unsupported version syntax is `unsupported_constraint`, not a skipped check. | §9 |
| 10 | Each policy node explicitly declares required `inputs`; non-package Stack and Corpus nodes declare an empty list. | §1, §12 |
| 11 | A full commit requires a local object or successful explicit fetch; `ls-remote` cannot prove historical commit existence. | §4.2 |
| 12 | Query the declared URL, not the checkout's origin; a normalized mismatch is also `policy_repo_mismatch` with `remote_mismatch`. | §3, §4.1 |
| 13 | Workflow `uses:` references use the same reference query/classification as package dependencies. | §4.1, §9 |
| 14 | Produce a reverse impact closure for every policy node. | §5 |
| 15 | Delegate PEP 440 evaluation to `packaging`; an unevaluable constraint remains unsupported. | §7, §9 |
| 16 | Every `--check` refreshes scan results, including its verdict and failure reasons. | §2 |
| 17 | Full verification bindings retain job- and step-level environment values and source lines. | §1 |
| 18 | Explicit branch/tag/rev selectors preserve their declared kind even when names collide. | §4.1 |
| 19 | A same-owner workflow or clone reference to an undeclared node is `policy_node_mismatch`; unrelated third-party actions are outside that node check. | §3, §5 |
| 20 | Required remote facts remain unverifiable when offline, for both CI and package references. | §4.2, §9 |
| 21 | A Git lock entry without a full commit SHA is `lock_missing`. | §4.3, §9 |
| 22 | Corpus tags use the shared reference lookup; only the expected-commit comparison is excluded. | §4.3, §6 |
| 23 | Deduplicate and sort edges by their complete identity, including normalized URL and declared selector. Different owners or selectors remain distinct. | §3, §5 |
| 24 | Parse workflow YAML with PyYAML, preserving comments' effect on values, quoting, escapes, flow mappings, block folding/chomping and source positions. | §1, §9 |
| 25 | Reject unsupported YAML structures, duplicate/merge keys, non-scalar environment values and other ambiguous inputs as `unsupported_workflow`. | §1, §9 |
| 26 | Pin parser dependencies and include their declaration in the input digest; reject an incompatible environment before generating artifacts. | §1, §2, §11 |
| 27 | Installed package versions and other environment observations belong only in scan results. | §1 |
| 28 | Validate all four exact dependency declarations before checking installed versions; reject missing, duplicate, unknown or non-exact entries. | §2, §11 |
| 29 | Argument parsing and preflight use only the standard library; `--help` works without a prepared workspace or third-party packages. | §2, §11 |
| 30 | Recognize actual `git clone` commands from Bash syntax trees after YAML decoding; quoted examples, comments and echo text are not dependency edges. | §5, §9 |
| 31 | Recursively validate `matrix`, `needs` and `runs-on`, including nested duplicate keys, merge keys and nonstandard scalar tags. | §1, §9 |
| 32 | Mask Actions expressions with words that preserve argument positions; respect strings inside expressions, and never persist placeholders in URLs, edges or plans. | §5, §9 |
| 33 | Decode static shell quoting, escapes and line continuations; variable, command and arithmetic expansions remain dynamic, including inside double quotes. | §5, §9 |
| 34 | A dynamic clone target or unrecoverable Bash syntax is `unsupported_workflow`; retain independent static clones and treat `--opt=value` as self-contained. | §5, §9 |
| 35 | Preserve ANSI-C quoted arguments as single words. Literal content without escapes can be static; escaped targets remain unsupported. Diagnostics identify the `run` source line. | §5, §9 |
| 36 | Accept and normalize HTTP(S), SSH, Git and SCP-style remote URLs consistently, including arbitrary SCP usernames, scheme case and trailing slashes. Local/file/package URL forms remain outside clone-edge modeling. | §5, §9 |
| 37 | Derive the published plan from isolated clones of each policy node's remote default branch; the derivation layer itself does not select branches or query the network. | §2.2, §11 |

## 1. Artifacts and self-reference

The committed plan contains policy-keyed nodes, including isolated meta/data
nodes; six edge kinds with declared refs, pinned identities and purposes;
workflow/job/step verification bindings with decoded environment values and
source lines; policy metadata; structural diagnostics; and `inputs_digest`.
Quoted commas, Actions expressions and block scalar values must not be truncated.

The plan excludes observed HEADs, checkout/common-directory paths, timestamps,
network observations and current floating-reference resolutions. The ignored
scan contains those observations, normalized actual remotes, query failures,
execution environment, alternate worktrees and deduplication results.

Committing the plan therefore cannot invalidate it merely by changing Stack's
HEAD. The digest excludes the plan itself and covers selected workspace-relative
input paths and their bytes:

- Each node's declared `inputs`, normally `pyproject.toml` and `uv.lock`.
- Workflow YAML and configuration selected by declared edge sources.
- Dynamically declared version-source files, such as `src/docx/__init__.py`.
- `ci/ecosystem-inventory-requirements.txt`, which pins the inventory toolchain.

A missing required input is an error. Stack and Corpus are not Python packages
and declare no package inputs.

## 2. Write and check behavior

`--write` derives and writes the plan, including structural diagnostics. It
returns zero when generation succeeds; regeneration does not fix diagnosed
problems. Failure to measure a required fact preserves the existing plan,
writes a failure scan and returns nonzero.

`--check` succeeds only when regenerated plan bytes match the committed plan,
structural diagnostics have no errors, and scan diagnostics have no errors or
unverifiable required facts. It refreshes `scan.json` on success and failure,
including `check.result`, `check.problems` and the byte-comparison verdict.
Dependency preflight failures occur before either artifact is written (§11).

| Severity | Meaning | Normal check | Strict check |
| --- | --- | --- | --- |
| `error` | Requires correction | Fail | Fail |
| `warning` | Policy concern with reproducible inputs | Pass | Fail |
| `unverifiable` | A fact could not be established | Fail if required | Fail |
| `info` | Observation | Pass | Pass |

### 2.1 Deterministic derivation

The plan is a deterministic function of selected input paths and bytes. Both
commands read primary checkout files, including uncommitted edits. Identical
inputs must produce identical bytes; an uncommitted pin change must affect the
comparison. An initial uncommitted policy can bootstrap generation. Reading
workspace bytes does not permit recording Git or machine state in the plan.

### 2.2 Published-plan basis

The published plan describes each policy node's remote default branch. This is
a workspace-preparation rule, separate from deterministic file derivation.

| Purpose | Entry point | Inputs |
| --- | --- | --- |
| Inspect a selected workspace | `make ecosystem-plan` / `make ecosystem-plan-check` | Caller-selected files, including local edits |
| Refresh or verify the published plan | `make ecosystem-plan-refresh` / `make ecosystem-plan-check-basis` | Isolated default-branch clones |

The refresh entry reads the node list from policy and clones each repository
normally. Do not hard-code `main`: some repositories use `master`. It invokes
the ordinary generator against that isolated basis. Write mode copies the
resulting plan back; check mode compares the caller's plan without changing that
caller's files. The inner check still records a scan in its isolated workspace.

Distinguish `plan bytes` differences from structural `plan counts` errors and
`scan counts` measurement failures. Only the first is a byte-drift result;
other failures require their own diagnostic investigation.

## 3. Node identity

A node ID is its stable policy key, normally matching `<root>/<key>`. Nodes and
edges in the plan use those keys. Scan maps keys to actual repositories,
normalized remotes, common directories and checkout paths.

- `policy_node_mismatch` is structural: a configured dependency names a node
  absent from policy. It does not depend on Git checkout discovery.
- `policy_repo_mismatch` is observational: a required checkout is missing, an
  undeclared local repository exists, or the remote differs from policy. Record
  `missing_checkout`, `undeclared_local` or `remote_mismatch` with the key.

Both categories block checks. Common-directory identity is used only for local
worktree deduplication in scan results.

## 4. References and detection boundaries

### 4.1 Classification follows query results

| Kind | Evidence | Reproducible | Diagnostic |
| --- | --- | --- | --- |
| `annotated_tag` | Tag and peeled `^{}` ref exist; use peeled commit | Yes | None |
| `lightweight_tag` | Tag exists without a peeled ref | Yes | None |
| `full_commit` | Forty hexadecimal characters and an existing object | Yes | `non_release_ref` warning |
| `branch` | Matching branch ref exists | No | `unreproducible_ref` error |
| `no_ref` | Git dependency has no declared ref | No | `unpinned_dependency` error |
| Query failure | Network or authentication prevents lookup | Unknown | `unverifiable` |

### 4.2 Missing versus unverifiable

A successful query proving a tag absent yields `missing_ref`. Network or
authentication failure yields `unverifiable`, which blocks required facts.
`ls-remote` cannot prove that an arbitrary historical commit exists. A full SHA
requires a local object or an explicitly allowed successful fetch. If neither
is available, report `unverifiable`, never `missing_ref`.

### 4.3 Detecting a changed target

`lock_commit_mismatch` requires a recorded expected SHA from `uv.lock`,
`ci/environment.json` or an explicit policy pin. Compare the resolved target
with that expected identity. A tag-only reference without an expected SHA can
record its current target and the absence of an expectation; it cannot prove
historical tag movement. This contract adds no reference-history database.

## 5. Edges and graph views

Edge kinds are `runtime`, `dev`, `codegen`, `ci`, `data` and `release`. Use one
`traverse(graph, start, edge_filter)` implementation with two policy-keyed views:

- Test impact: reverse closure over runtime/dev/codegen/ci/data; cycles allowed.
- Partial release order: forward runtime/codegen edges; assert acyclicity.

Filter edges instead of duplicating traversal logic. Preserve complete edge
identity, including normalized URL and declared selector, during deduplication
and sorting. Clone recognition analyzes Bash syntax without executing commands.

## 6. CI snapshots and corpus data

Engine's `ci/environment.json` declares CI repository snapshots. Model those
references as `ci` edges with purpose `engine_ci_snapshot` and include them in
test impact. Every declared repository snapshot participates, including Apps,
Core, Corpus, Spec, Stack, Stubs, Test Framework and the three format libraries.

A Corpus data edge records its declared release tag, the declaring file/field,
and its configured Git commit separately:
`{policy_key, purpose, declared_release_tag, tag_source, pinned_commit}`.
Use normal reference lookup for tag existence and classification, but do not
compare the data tag with the configured code commit or derive a mismatch from
their difference. A data release and a Git snapshot need not identify the same
thing. Runtime/codegen ordering is partial; real releases may also need upstream
dev-dependency tags to exist.

## 7. Version-skew scope

Group all configured dependencies by `(upstream, role)`, with runtime, dev,
codegen and CI roles. Different versions across consumers in the same group
produce a `version_skew` warning. Policy can declare `require_uniform` scopes
and named `exceptions`; undeclared groups must still be examined and reported.

Record upstream, role, repositories with versions/refs, policy scope and matched
exceptions. Do not infer a cross-role violation from version differences alone.
A declared constraint or lock conflict is a separate `constraint_violation`
error. Two consumers using different development versions are same-role skew,
not evidence of a runtime/development mismatch.

## 8. Apps participation

Apps belongs in the node set and impact graph because it consumes Engine. Keep
its runtime dependency in partial release ordering. Actual release participation
is an explicit policy choice. Internal release execution lists, including
auxiliary-worktree lists, do not define or erase dependency facts.

## 9. Diagnostics and historical observations

| Structural code | Severity | Trigger |
| --- | --- | --- |
| `unpinned_dependency` | error | Git dependency has no ref |
| `version_skew` | warning | Different versions within an upstream/role group |
| `constraint_violation` | error | Pin violates a declared constraint or lock |
| `unsupported_constraint` | error | Constraint cannot be evaluated, such as `^1.0` |
| `lock_missing` | error | Dependency is absent from lock, or its Git entry lacks a full SHA |
| `source_override_conflict` | error | Conflicting source selectors or URLs |
| `policy_node_mismatch` | error | Configuration references an undeclared node |
| `missing_input` | error | An explicitly required input is absent |
| `command_source_mismatch` | error | Declared full verification disagrees with workflow steps |
| `unsupported_workflow` | error | Unsupported YAML structure, invalid nested keys/tags, malformed Actions/Bash syntax or a dynamic clone target |

| Scan code | Severity | Trigger |
| --- | --- | --- |
| `missing_ref` | error | Successful lookup proves a reference absent |
| `unreproducible_ref` | error | Reference is a branch |
| `non_release_ref` | warning | Reference is a full commit SHA |
| `lock_commit_mismatch` | error | Resolved target differs from a recorded expected SHA |
| `floating_ci_ref` | error | Workflow uses a floating branch such as `@main` |
| `policy_repo_mismatch` | error | Actual repository differs from policy; include direction |
| `unverifiable` | error if required, warning otherwise | Lookup or commit verification cannot complete |
| `duplicate_repo_identity` | info | Worktrees share repository identity |
| `alternate_worktree` | info | Checkout is not the primary checkout |

The original pre-repair scan recorded these historical results:

| Code | Count | Original observation |
| --- | --- | --- |
| `unpinned_dependency` | 1 | Apps declared Engine without a ref |
| `version_skew` | 2 | Core runtime 0.3.51/0.6.0; Test Framework dev 0.5.21/0.5.37 |
| `missing_ref` | 3 | Format-library pins named unavailable `v0.5.37`; the highest remote tag was `v0.5.35.post1` |
| `lock_commit_mismatch` | 2 | DOCX/Stubs locks recorded `b0edf01`; `v0.6.0` resolved to `cde719c` |
| `floating_ci_ref` | 5 | Apps, Stack and the three format libraries used floating shared actions/workflows |
| `alternate_worktree` | 41 | Alternate local checkouts |

Separately authorized repairs on 2026-09-13 retained Framework 0.5.37 at its
existing lock commit `347808e0b41cd88a8cb257e809276ec8c35acd0d`, pinned Apps to
its existing Engine commit `289eee5bac8fb38bc0e589f00a06ceb65293488b`, regenerated
DOCX/Stubs Core locks at the actual tag target
`cde719c0c6625da903a38c66752d2fe30995e5b7`, and pinned shared action/workflow
callers to complete SHAs. Shared CI changes preceded their callers; tags were
not moved. Regeneration retained SHA-reference and version-skew warnings, so
strict checks could still fail. Historical failures do not explain new errors.

## 10. Acceptance criteria

### Positive cases using a fixture without drift

1. Write, commit the plan, then check successfully: no self-reference failure.
2. Peel annotated tags to commits correctly.
3. Adding/removing worktrees leaves plan bytes unchanged; deduplication stays in scan.
4. Include isolated meta/data nodes.
5. Consecutive writes produce identical bytes.
6. Moving the workspace root leaves plan bytes unchanged.
7. An alternate worktree does not affect the plan.
8. Identical uncommitted input bytes still generate identical output.
9. Plan structure excludes observed remotes, common directories, HEADs, times and current ref resolutions.
10. A fresh venv without inherited packages can be prepared explicitly, run the CLI and pass a drift-free write/check; missing or wrong dependencies fail without replacing the plan.
11. YAML environment values retain comments' parsing effects, escaped quotes, folding and chomping; assert field values, not just exit codes.
12. Inline, literal-block and folded-block static clones produce equivalent CI edges and reverse impact, passing strict checks.
13. Valid matrix include/exclude, anchors/aliases and expressions survive recursive conversion; needs/runs-on use the same validation.

### Refusal and boundary cases

1. An uncommitted pin edit changes derived bytes and fails comparison.
2. Detect a moved tag when a recorded expected SHA exists.
3. Reject a lock SHA that differs from the tag's resolved commit.
4. Branch refs produce `unreproducible_ref`.
5. Missing refs produce `unpinned_dependency`.
6. Removing a referenced policy node produces structural `policy_node_mismatch`.
7. A successfully queried absent tag is `missing_ref`, not `unverifiable`.
8. Network failure is `unverifiable`; required facts fail by default.
9. Preserve the original failing scan; the repaired online check must pass without suppressing warnings.
10. Missing required or undeclared local repositories produce blocking `policy_repo_mismatch` scan errors.
11. A tag-only reference without an expected SHA cannot establish historical movement; record its current target without `lock_commit_mismatch`.
12. Nested-map environment values produce `unsupported_workflow`, not guessed strings.
13. Invalid YAML produces `unsupported_workflow`, not an empty workflow.
14. Installed dependency versions differing from declarations cause exit 2 without replacing the plan.
15. Empty/comment-only declarations, missing packages, alias duplicates, unknown packages or non-exact syntax cause exit 2 without changing or creating plan/scan artifacts.
16. Missing packages in a fresh venv produce an actionable preparation command and no traceback; `--help` still succeeds.
17. Names/with-fields, comments, echo text, quoted commands/separators and local clone paths produce no remote clone edges. Real commands after actual separators are still recognized.
18. Duplicate matrix keys or custom tags, including nested needs/runs-on values, produce an error recorded by write and rejected by normal/strict checks.
19. Masked Actions expressions preserve argument position and independent clones under both `|` and `|-`; quoted `}}` inside an expression does not end it early.
20. Static escaped arguments such as `ooxml\-native-corpus.git` decode to the correct repository without a false node mismatch.
21. Dynamic `${REPO}` or `${{ inputs.repo }}` clone targets produce `unsupported_workflow`, no guessed edge and no node mismatch; write records it, check fails, and independent static clones remain. Unrecoverable Bash syntax is also rejected.
22. Double-quoted expansions remain dynamic; quoted static URLs remain static. `--branch=${{ inputs.ref }}` and other `--opt=value` arguments do not consume the following URL.
23. HTTP(S), Git, SSH and SCP-style remotes, uppercase schemes and trailing slashes normalize consistently. Local clone paths remain outside the edge model.

## 11. Implementation scope and dependency preparation

The inventory implementation owns its Makefile entries, ignored scan/venv
paths, policy, pinned dependency files, `scripts/ooxml_ci/`, its tests, generated
plan and this specification. It does not automatically modify other repositories'
CI, package declarations, locks or hooks; repair operations require their own
scope. It does not introduce execution runners, hooks, locks or concurrency.

The parser uses four explicitly pinned third-party packages:

```text
packaging==26.0
PyYAML==6.0.3
tree-sitter==0.26.0
tree-sitter-bash==0.25.1
```

`packaging` evaluates PEP 440. PyYAML `compose` reads node trees without
constructing application objects. Tree-sitter identifies Bash commands and
arguments without execution. Do not substitute handwritten version comparison,
YAML parsing or shell tokenization. `shlex` alone loses distinctions between
quoted separators/examples and executable command boundaries.

Actions expressions are masked before Bash parsing, preserving word positions.
This prevents dynamic option values or earlier expressions from swallowing
subsequent static clone targets. Placeholders never enter persisted identities.
Unrecoverable syntax after masking is rejected. The original implementation run
parsed 452 run bodies after this adaptation; that is a historical observation.

Prepare the declared dependencies explicitly from the workspace root:

```bash
cd ooxml-stack
make ecosystem-inventory-deps
# Equivalent preparation:
# python3 -m venv .venv-ecosystem-inventory
# .venv-ecosystem-inventory/bin/python -m pip install -r ci/ecosystem-inventory-test-requirements.txt
```

Use the Makefile's prepared interpreter for inventory commands:

```bash
make ecosystem-plan
make ecosystem-plan-check
make ecosystem-inventory-test
make ecosystem-plan-refresh
make ecosystem-plan-check-basis
```

Test requirements add `pytest==9.0.2`. Neither write nor check installs packages
implicitly. Preflight first validates exactly one `name==version` declaration
for each of the four parser packages, using normalized distribution names.
Reject empty/missing/duplicate/unknown entries, ranges, `===`, extras, markers
and include directives in that runtime declaration. Then compare installed
versions. Failure exits 2 before plan/scan writes and prints preparation steps.
Do not assume pip or setuptools provides an importable top-level `packaging`.

The argument-parser, workspace and dependency-preflight import chain uses only
the standard library. Third-party imports happen after preflight. Package-version
changes can alter constraint results, so pins are part of the contract; observed
installed versions belong only in the scan.

## 12. Implementation organization

1. Policy declares nodes, edge sources, uniformity requirements, exceptions and release participation.
2. Inventory modules select/hash inputs, parse configurations, derive nodes/edges, group skew, diagnose structure and serialize the plan. Ownership is split among `paths`, `inputs`, `parsers`, `yamlnodes`, `workflows`, `bashwords`, `deps`, `facts`, `edges`, `ciedges`, `versions`, `graphs`, `full`, `plan`, `gitfacts`, `scan` and `cli`.
3. Scan handles reference queries, expected-commit comparisons, repository mismatch and worktree identity. Git/network observations stay outside deterministic plan derivation.
4. Both graph views share traversal and use their declared edge filters and cycle rules.
5. Tests cover the positive, refusal and boundary cases in §10; original failures remain historical evidence.

Keep implementation files below 300 lines and functions below 50 lines.
