# ooxml-stack Agent Notes

## Capability Claims

- Read `docs/OOXML-ELEMENT-CAPABILITY-LEDGER.md` before making OOXML
  compatibility, readability, editability, or full-write claims.
- Use capability names and measured denominators in user-facing docs. Do not use
  internal phase IDs as public claim language.
- Treat historical `release-evidence/p*/` directories as replayable audit
  sources, not as the primary status surface.
- Keep ad hoc run outputs, batch artifacts, and internal phase evidence out of
  git unless they are deliberately promoted into a public release evidence
  bundle with a manifest and locked profile.

## Large Evidence Workflow

- Do not push repeated intermediate rewrites of large generated ledgers such as
  `release-evidence/**/promotion-rows.jsonl`.
- Before pushing a long evidence campaign, squash local checkpoint commits or
  regenerate mutable aggregate ledgers once in the final publish commit.
- Keep per-chunk evidence files and Office gate results as replayable audit
  inputs; treat aggregate ledgers as derived publish artifacts.
