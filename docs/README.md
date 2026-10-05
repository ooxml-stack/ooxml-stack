# Documentation

## Product and evidence contracts

- [Architecture](ARCHITECTURE.md): product surfaces, repository owners and
  dependency boundaries.
- [Capability claims](CAPABILITY-CLAIMS.md): how to describe reading, editing,
  preservation and audit evidence.
- [Compatibility contract](COMPATIBILITY-CONTRACT.md): the existing DOCX/PPTX
  supported-valid-file contract and its limits.
- [Public content policy](../VISIBILITY.md): publication, provenance and licenses.

## Maintainer entry points

- [Maintainer guide](MAINTAINING.md): directory ownership and verification commands.
- [Developer worktrees](DEVELOPER-WORKTREES.md): workspace initialization and
  recorded task checkouts.
- [Shared workspace rules](WORKSPACE-AGENTS.md): rules installed at workspace root.
- [Shared runner](ECOSYSTEM-RUNNER-SPEC.md): request identity, adapters and receipts.
- [Dependency inventory](ECOSYSTEM-INVENTORY-SPEC.md): policy, plan derivation and
  source identity checks.
- [Artifact storage](ARTIFACT-STORAGE.md): current placement and recovery rules.
- [Evidence blob storage](EVIDENCE-ARTIFACT-STORE.md): deduplication within an
  external evidence store.
- [Artifact archive index](ARTIFACT-ARCHIVE-INDEX.json): provenance of previously
  tracked artifacts, not a new verification run.

## Historical records

These records keep their original paths for citations and replay. Counts,
commands and conclusions describe their recorded revisions and environments.
Use the current storage and public-content rules when handling their artifacts.

| Record | Recorded scope |
| --- | --- |
| [Mutation coverage closeout](P97-PHASE-CLOSEOUT-NEXT-STEPS.md) | Selected compliance-rule mutation evidence |
| [Additional mutation coverage](P98-PHASE-CLOSEOUT.md) | Further rule families, coverage budget and native-check limitations |
| [Public-release hygiene review](P99-PHASE-CLOSEOUT.md) | Historical current-tree and history audit; an export proposal, not current publication clearance |
| [Local integration, 2026-09-26](LOCAL-INTEGRATION-20260926.md) | Mutation-fixture and budget verification |
| [Release profiles](../release-profiles/) | Historical verification inputs with retained identities |

Historical package paths may refer to files now held externally. Their absence
from a clone is not a passing result. See [artifact storage](ARTIFACT-STORAGE.md)
for recovery before attempting a replay.
