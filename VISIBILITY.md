# Public content policy

This repository is a public coordination and shared-engineering surface. Its
tracked runner, scripts and workflows are part of that scope. Office execution
internals, private datasets and environment-specific operational records remain
with their owning repositories or external evidence stores.

## Content that belongs here

- Product positioning, repository responsibilities and interface boundaries.
- Compatibility contracts and capability-claim rules with explicit limitations.
- Shared runner, inventory and workspace tooling, with regression tests.
- Generic CI workflows, reusable actions, dependency declarations and pinned
  source identities needed to review those tools.
- Maintainer instructions using placeholder paths and environment variables.
- Small, immutable, redistributable test fixtures actually consumed by tests.
- Historical specifications and profile identities, clearly distinguished from
  current release evidence.

A repository name, source commit or credential variable name can be needed to
explain a public tool's contract. It does not grant access to a private repository
or permission to distribute its contents. Never include credential values.

## Content that stays out

- Tokens, private keys, authenticated URLs, credential files and secret values.
- Real machine paths, LAN addresses, personal usernames or access instructions
  for an individual deployment.
- Customer documents, private Office corpus files and restricted template assets.
- Raw model transcripts, task answers, private evaluation inputs and generated
  run evidence, including screenshots and Office output packages.
- Private runtime source, business configuration or unreleased implementation
  details copied from another repository.

Store generated evidence according to [artifact storage](docs/ARTIFACT-STORAGE.md).
An external location is a storage decision, not permission to publish its files.
A public example requires its own provenance and redistribution rights; a corpus
fixture does not become public-safe merely by being small or used in a test.

## Review before publication

Review changed contents, their provenance and their dependencies. Git tracking,
an LFS attribute, a filename extension or a passing hygiene scan does not prove
that a file may be published. Review the actual files selected for export.

Current-tree checks and history checks have different scopes. An edited README,
a removed file or a clean current-tree scan does not remove previously published
history. Historical audit results apply only to the recorded input and time;
they do not authorize a fresh export or establish current full-history safety.

## Licenses and claims

This policy does not add or change a software license, relicense third-party
work, or open any private repository. Preserve applicable copyright notices and
licenses when distributing components. A public repository without an applicable
license is not automatically an open-source distribution.

Apply [capability-claim rules](docs/CAPABILITY-CLAIMS.md) to public product text.
Report supported scope, tested identity and limitations rather than inferring
product readiness from schema coverage, historical counts or a green tool test.
