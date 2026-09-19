# Shared Ecosystem Runner

The shared runner turns one request into one verifiable fact:

```
(repository, commit, runner commit, plan) -> report
```

A report is evidence only when it names the commit, the runner version, the plan
identity and the inputs it was produced from, and when a verifier re-derives
those values from the caller's arguments instead of trusting the report.

## Scope

`ooxml_runner` is a top-level package in this repository. It is deliberately not
`scripts.ooxml_runner`: neither this repository nor `ooxml-operation-engine` has
a `scripts/__init__.py`, so `scripts` resolves as a PEP 420 namespace package
spanning both checkouts. That happens to work today and is path-order fragile, so
the runner does not depend on it.

The runner owns:

- resolving a commit to a full commit id and materializing a clean snapshot;
- launching the pinned execution container and streaming its log;
- the stage protocol: ordering, per-stage deadlines, status transitions,
  durable report writes and progress events;
- verifying that the run did not move its own inputs or leave the snapshot dirty;
- verifying a finished report against the request.

The runner does **not** own any repository's checks. Those arrive through an
adapter, which the ecosystem plan names.

## The plan is an input, not a script

The plan (`ci/ecosystem-plan.json`) is read for three things:

1. proving the target repository is a declared full-verification node and that
   its declared workflow and job still exist;
2. naming the adapter that owns the repository's checks;
3. binding the run to a plan file identity (SHA-256) and to the configuration
   identity the plan was derived from (`inputs_digest`).

The plan's shell text is **never executed**. A workflow step that calls the
shared entry is evidence that the binding is wired up, not a command to run;
running it would re-enter the runner.

`inputs_digest` is re-derived from the workspace whenever every declared input is
present. A mismatch fails the run. When inputs are absent - a repository's own CI
checks out only part of the ecosystem - the report records
`inputs_reverified.verified = false` with the reason, rather than claiming a
verification that did not happen.

Every declared input is compared against its own recorded digest, and the report
says what happened to each one:

| Situation | Recorded as |
| --- | --- |
| present, digest matches | `checked` |
| present, digest differs | the run fails closed, however many others are absent |
| absent | `unchecked`, named in `unchecked_paths`, never counted as a pass |
| the target repository's own | `excluded`, with the reason and the commit it is bound to |

`inputs_reverified.verified` means the applicable scope is **complete**: every
declared input is either checked and matching, or excluded with a reason. A
repository's own CI checks out only part of the ecosystem, so it leaves inputs
`unchecked` - that is honest partial evidence, and `verified` is `false` there.

The target repository's own inputs are excluded because they are already bound
twice over: by the commit being verified, and by the report's own `inputs` (the
adapter's input hashes, re-derived from a clean snapshot of that commit). Reading
them from the caller's working tree would let an uncommitted edit change the
verdict for a historical commit. The exclusion is a statement about the plan
baseline, **not** a proof that the target commit's bytes equal the recorded ones,
so each excluded entry names the commit it is bound to. The plan's `full` binding
is likewise derived from the baseline, not re-derived from the target commit.

`verify-report` re-derives the scope from the trusted plan and the workspace it is
verifying against, so a report cannot declare its own exclusions: naming an
external repository's inputs as "the target's" would otherwise skip comparing
them.

## Adapters

An adapter is a Python module named by the plan's full binding. It must expose:

| Name | Purpose |
| --- | --- |
| `describe(root)` | static contract: stage list, environment, where the bodies live |
| `load_config(root)` | validated environment declaration |
| `input_hashes(root)` | files whose change invalidates a report |
| `operations(root, reports, config)` | ordered stage-name to callable mapping |
| `verify_report(report, commit, config, inputs)` | the repository's own report contract |
| `is_dirty(root)` | whether the run left its snapshot modified |

The runner fails closed when the module is missing, does not import, omits a
protocol name, declares no stages, declares duplicate stages, or implements a
different stage order than it declares.

Adapters are loaded from their file with a name unique to that checkout. Loading
`scripts.ci.adapter` by dotted name would return whichever module was imported
first, so a second repository could silently run the first one's checks.

## Report

The report extends the shape the engine already wrote. Verifiable identity is
added; the historical stage contract is unchanged.

```json
{
  "schema_version": 1,
  "status": "pass",
  "repository": "ooxml-operation-engine",
  "commit": "<40 hex>",
  "runner": {"commit": "<40 hex>", "source_sha256": "<64 hex>"},
  "plan": {"path": "...", "sha256": "<64 hex>", "inputs_digest": "<64 hex>",
           "inputs_reverified": {
             "verified": true, "total": 49, "checked": 43, "unchecked": 0,
             "unchecked_paths": [],
             "excluded": [{"path": "ooxml-operation-engine/pyproject.toml",
                           "reason": "target_repository", "bound_to": "<40 hex>"}],
             "reason": "43 of 49 plan inputs checked; 6 excluded ..."}},
  "binding": {"workflow": "...", "jobs": ["check"], "adapter": "scripts.ci.adapter"},
  "image": "<digest-pinned image>",
  "inputs": {"<path>": "<sha256>"},
  "started_at": "...", "finished_at": "...", "exit_code": 0,
  "stages": [{"name": "...", "status": "pass", "seconds": 1.23, "artifacts": ["..."]}]
}
```

`progress.jsonl` records `gate_started`, `stage_started`, `stage_passed` /
`stage_failed`, and `gate_passed` / `gate_failed`. A failure report is written
before the event that points at it, so a crash between the two still leaves a
consistent scene. `gate_passed` is emitted only after every stage passed, the
inputs are unchanged and the snapshot is clean.

## Verification

`verify-report` re-derives what the report is checked against:

```
python3 -m ooxml_runner verify-report \
  --root <workspace> --repo ooxml-operation-engine --commit <sha> \
  --runner-commit <sha> --plan <path> --report <report.json>
```

The expected repository, commit, runner commit, plan SHA-256, inputs digest and
stage list all come from the caller and from the repository at the requested
commit. A report never passes on its own `status` field alone.

`plan.inputs_reverified` is re-derived the same way, so the scope claim is checked
rather than believed: a report that claims completeness over a workspace with
unchecked inputs, omits the block, miscounts, or widens the excluded set to cover
another repository's inputs is refused. The report is never rewritten.

## Cache reuse

Reuse is opt-in (`--reuse-success`) and requires a prior report that matches the
commit, runner commit, plan SHA-256, inputs digest **and** the repository's own
report contract. The default is a full run. A malformed report never hides a
valid one; the search continues past reports that fail verification.

## Entry points

```
python3 -m ooxml_runner describe      ...
python3 -m ooxml_runner run           ...
python3 -m ooxml_runner verify-report ...
```

`describe` starts nothing: no Docker, no credentials, no checks. It is evidence
that the request is well formed, never evidence that the gate passes.

## Onboarded repositories

Only `ooxml-operation-engine` declares an adapter. A node without one is not an
error - it has simply not been onboarded yet - but the runner refuses to execute
it rather than inventing a way to run its workflow text. The claim supported
today is exactly: *the engine verifies through the shared runner, and its local
and CI runs call the same full-verification entry.*