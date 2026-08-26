# P99 — Public Release Hygiene (phase closeout)

This document records the P99 public-release-hygiene slice of the
compatibility contract, following the P97/P98 evidence phases. It states what
was audited, what changed, the public-safety boundary, and the release vehicle
decision. It makes **bounded** claims only — no claim of full-history public
safety, no claim that every working repo is sanitized.

## Scope

P99 is about the public-release path: confirming the current tracked tree is
clean of local user paths, measuring full-history safety, deciding whether to
release from current history or a fresh public mirror, and keeping large /
private historical evidence out of the public release paths.

Boundaries (do not over-claim):

- P99 does **not** claim full Git-history public safety from this branch.
- P99 does **not** sanitize the entire working history of sibling repos.
- P99 does **not** rewrite git history; history filtering is out of scope by
  project constraint.

## Machine audit (evidence)

```bash
make repo-hygiene                     # == python3 scripts/audit_repo_hygiene.py
```

Output (gitignored, regenerated each run):
`artifacts/ooxml-stack-full-history-hygiene-audit.json`.

Authoritative numbers from the P99 run (`ooxml-stack`, main):

| Metric | Value |
| --- | ---: |
| Current worktree local-user-path hits | 0 (after redaction) |
| Current raw release-evidence user-path hits | 0 |
| Current normal Git blobs over 10MB | 0 |
| Full-history user-path blobs | 66 |
| Full-history secret-like blobs | 0 |
| Full-history blobs over 10MB | 540 |
| Full-history blobs over 50MB | 91 |
| Full-history blobs over 100MB | 1 |
| Historical blobs scanned | 17 814 / 18 005 |
| `.git` object store size | ~7.8 GB |

`recommended_public_release_option`: **fresh_public_mirror**.

### Finding: current worktree leaked local paths (fixed)

The fresh audit found the **current** tracked tree was not public-safe: five
committed `release-profiles/` files embedded the editing/home path in an env
value:

- `release-profiles/p91-xlsx-baseline.json`
- `release-profiles/p92-xlsx-active-editability.locked.json`
- `release-profiles/p93-xlsx-preserve-and-compliance.json`
- `release-profiles/p94-xlsx-compliance-clean.json`
- `release-profiles/p95-docx-pptx-compliance.json`

Each held `OOXML_*_SOURCE_DIR` pointing at the editing host's
`<home>/Downloads/test_docs/<fmt>` (a local absolute path). These are
machine-entered config defaults in `release-profiles/` (not
`release-evidence/`), so the evidence redaction script did not cover them.

**Fix (P99):** redacted the absolute paths to a portable placeholder
(`<home>/Downloads/test_docs/<fmt>`) in all five files, preserving JSON
structure. After the change the audit's current-tree home-path grep returns 0
and `current_worktree.user_path_hit_count` is 0. These redactions correct the
earlier readiness closeout, which had recorded current user-path hits as 0 —
that was an audit-scope miss. The P99 measured value (0) is the correction.

> The audit's current-tree check is a fixed-string grep for the home-user path
> token over all tracked files, and does cover `release-profiles/`; the earlier
> readiness close reflected a narrower view. Redaction now makes the current
> tree clean of local absolute paths.

**Second blind spot — `/tmp/` absolute paths (resolved by redaction):** the
audit only greps the home-path token, so `/tmp/...` absolute paths in
`release-profiles/` env values were not flagged. These are not a privacy leak
(no username) but are the same class of **non-portable** local path — a fresh
clone could not resolve them. Per the reviewer's either/or, redaction was
chosen over a boundary carve-out: portability is the goal, so `/tmp/<name>`
was rewritten to `<tmp>/<name>` in `p15-zero-warning.json` (3),
`p94-xlsx-compliance-clean.json` (1), `p95-docx-pptx-compliance.json` (3,
incl. a prose note), and `p96-all-formats-compliance-clean.json` (3), 10 in
total. No `/tmp/` nor home-user path remains under `release-profiles/`.

## Sibling repos

Other project repos show many current-tree home-user path hits in **agent-session
notes and fixtures** (e.g. `python-xlsx/.opc/loop-session-round1-done/*.md`),
not in shipped library source. Sanitizing every working repo's operational
notes is out of P99 scope. This reinforces the **fresh public mirror** decision:
the release vehicle is a curated mirror of public-safe artifacts, not the
un-sanitized full working history of each repo.

## Decision: fresh public mirror

Because the full history of `ooxml-stack` is not public-safe (540 oversized
blobs, 66 user-path blobs) and sibling repos carry operational notes with local
paths, the release vehicle is a **fresh public mirror** rather than the current
branch history.

### Mirror procedure (concrete)

1. Create a new public repo (e.g. `ooxml-stack-public`) with no migration from
   the private pack.
2. Export only the current tree as a single source snapshot:
   `git archive --format=tar HEAD:main | tar -x -C <stage>` (or
   `git checkout` of the release tag).
3. Build the mirrored repo with one squashed/initial commit from that clean tree
   — no historical blobs are carried.
4. Include / exclude by the LFS boundary: copy only **plain-git** files (the
   `.gitattributes`-untracked-by-LFS set) and **omit every LFS-tracked file**.
   Concretely, from `git archive`:
   - **Include:** source, `scripts/`, `tests/`, `docs/`, `release-profiles/`
     (redacted), and `release-evidence/**/*.json` summaries (e.g.
     `p98/rule-coverage-mutation-gate-summary.json`, `p98/manifest.json`,
     `p98/coverage-budget-baseline.json`, `p98/office-verification/*.json`).
   - **Exclude (never copy to the mirror):** every LFS-tracked file — all
     `release-evidence/**/*.jsonl` (and `*.jsonl.part-*`) rows and all Office
     binary packages under `release-evidence/**` (`*.docx` / `*.pptx` /
     `*.xlsx`). These are derived/large operational artifacts out of public
     scope; the JSON summaries above are the portable evidence surface.
   - The boundary is enforced by `.gitattributes`: anything `filter=lfs` stays
     out; anything committed as a normal blob is eligible. When staging, drop
     the `.git/lfs` objects and any file whose path matches the LFS patterns.
5. Confirm the mirror tree passes `make evidence-hygiene` and
   `python3 scripts/audit_repo_hygiene.py`.
6. The `release-profiles/` redactions (`<home>/...` and `<tmp>/...`) are already
   in-source and the mirror inherits them, so no profile still references a
   host-specific absolute path.

### What this does / does not claim

- Does claim: the current tracked tree (after redaction) is free of both
  home-user and `/tmp` absolute paths in `release-profiles/`; the fresh mirror
  so built carries no historical oversized/user-path blobs and no profile with
  a host-specific absolute path.
- Does not claim: full-history public safety of the private branch, or that
  every sibling working repo is sanitized.

## Files

- This document: `docs/P99-PHASE-CLOSEOUT.md`
- Changed (portability redaction of `release-profiles/` env values):
  - Home path → `<home>/...`: `p91-xlsx-baseline`, `p92-xlsx-active-editability.locked`,
    `p93-xlsx-preserve-and-compliance`, `p94-xlsx-compliance-clean`, `p95-docx-pptx-compliance`
  - `/tmp` → `<tmp>/...`: `p15-zero-warning`, `p94-xlsx-compliance-clean`,
    `p95-docx-pptx-compliance`, `p96-all-formats-compliance-clean`
- Audit output (gitignored): `artifacts/ooxml-stack-full-history-hygiene-audit.json`

## Validation

- `python3 scripts/audit_repo_hygiene.py` → `public_safe_current_worktree` true
  (user-path hit 0, no large index blobs, LFS clean), `public_safe_full_history`
  false, recommended mirror.
- `make evidence-hygiene` → green (unchanged; redaction is under
  `release-profiles/`, evidence path untouched).
- Full `python3 -m pytest tests` → green (unchanged; no test references the
  redacted env values).