# OOXML Stack

OOXML Stack is an umbrella for high-fidelity Office Open XML tooling.

This public repository is intentionally limited to non-sensitive project-level
information. It does not contain runtime source code, validation internals,
private datasets, release operations, CI infrastructure, or access setup.

## Scope

- Public positioning for the OOXML Stack project.
- High-level visibility policy for what may appear in public repositories.
- Contribution rules for this public coordination surface.

Implementation details, test corpora, operational runbooks, release gates, and
team installation instructions live outside this public repository.

## Status

The stack is under active private development. Public claims in this repository
are intentionally conservative and should not be treated as an API guarantee.

## Repository Contents

- `README.md` - public overview.
- `VISIBILITY.md` - public/private boundary policy.
- `CONTRIBUTING.md` - contribution and disclosure rules.
- `docs/COMPATIBILITY-CONTRACT.md` - public compatibility claim boundary.
- `docs/OOXML-ELEMENT-CAPABILITY-LEDGER.md` - stable capability ledger for
  measured OOXML readability/editability claims.

No generated Office files, private datasets, CI artifacts, secrets, or local
machine paths should be committed here.
