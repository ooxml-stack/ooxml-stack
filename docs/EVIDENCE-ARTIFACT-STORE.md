# Evidence Artifact Store

OOXML release evidence must not grow by copying full Office packages for every
API, CLI, MCP, batch, and public-path replay. The repository source of truth is:

- JSON/JSONL evidence rows with `output_file` and artifact metadata.
- Hashes, validation summaries, gate reports, and release claims.

The package-byte cache lives under
`release-evidence/artifact-blobs/sha256/<aa>/<bb>/<sha>.<ext>`. It is ignored by
git and should be treated as a local cache or CI artifact, not committed release
evidence. `release-evidence/artifact-blobs/artifact-manifest.jsonl` is a local
ledger for that cache; the committed JSON/JSONL rows carry the hash metadata
needed to audit release claims.

Generated `.docx`, `.pptx`, and `.xlsx` evidence paths may still exist for
compatibility with Office gates and existing reports, but they should be
hardlinks to the content-addressed blob after all writers and native Office
checks are finished.

Retention policy:

- Keep blobs for failures, release gates, pinned samples, and the latest active
  smoke/native gate runs.
- For older successful runs, keep JSON/JSONL rows, hashes, validation summaries,
  and claims; do not require per-path duplicate package bytes.
- New `.docx`, `.pptx`, and `.xlsx` files under `release-evidence/` are blocked
  by `scripts/check_evidence_retention.py` unless explicitly allowlisted in
  `release-evidence/RETAINED-ARTIFACTS.txt`.
- Use `scripts/plan_evidence_cleanup.py` to produce a dry-run cleanup report for
  older successful generated outputs before deleting any historical artifacts.
- Run `scripts/audit_evidence_artifacts.py --hash-content` before large evidence
  commits to measure duplicate logical bytes.
- Use `--apply-hardlinks` only after reviewing the dry-run summary. It preserves
  paths and bytes but changes inode layout.
