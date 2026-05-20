# Visibility Policy

Default stance: publish only the minimum information needed for public project
positioning.

## Public

This repository may contain:

- Project-level overview text.
- Public contribution and disclosure rules.
- Public-safe roadmap language with no operational details.

## Private

Keep the following out of this repository:

- Runtime source code and implementation internals.
- Validation internals, compatibility gates, and private test strategy.
- Office corpora, derived baselines, artifacts, and benchmark outputs.
- Release operations, CI topology, and deployment runbooks.
- Private repository inventory, package install instructions, credential names,
  run identifiers, commit evidence tables, and local filesystem paths.

## Review Standard

Before publishing, ask whether the content helps a public reader understand the
project without helping them infer private infrastructure or unreleased product
strategy. If not, keep it private.
