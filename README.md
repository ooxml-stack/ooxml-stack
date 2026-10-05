# OOXML Stack

Office document tools for agents: read and analyze document structure, apply
controlled edits, and audit the resulting changes across DOCX, PPTX and XLSX.
This is the project's direction; supported operations and compatibility claims
must be tied to a specific runtime release and its measured scope.

This public repository holds project documentation and shared engineering tools.
The Office runtime and the web application are maintained in separate
repositories. Cloning this repository does not install an Office editor, an MCP
server or a hosted service.

## Start here

| You want to… | Read |
| --- | --- |
| Understand the product and repository boundaries | [Architecture](docs/ARCHITECTURE.md) |
| Assess a reading, editing or audit claim | [Capability claims](docs/CAPABILITY-CLAIMS.md) |
| Understand file-preservation guarantees | [Compatibility contract](docs/COMPATIBILITY-CONTRACT.md) |
| Work on the shared tools | [Maintainer guide](docs/MAINTAINING.md) |
| Find current specifications or historical records | [Documentation index](docs/README.md) |
| Report a problem or propose a change | [Contributing](CONTRIBUTING.md) |

## Product boundaries

- **Operation Engine** owns document operations, structured results, validation
  and the CLI/MCP execution surface. Other interfaces reuse its contracts.
- **Apps** provides the HTTP gateway, document revisions, candidate review and
  the human-facing workbench.
- **Stack** coordinates repositories, dependency plans and verification. Its
  shared runner executes engineering checks, not agent Office tasks.

Runtime access and installation are governed by the runtime's own distribution
and license. This repository does not provide a public runtime download or grant
access to private packages. Public visibility alone is not an open-source
license for this repository or the rest of the ecosystem.

## What is in this repository

| Path | Responsibility |
| --- | --- |
| `docs/` | Architecture, contracts, maintainer specifications and historical records |
| `ooxml_runner/` | Shared verification runner and report identity checks |
| `scripts/` | Dependency inventory, worktree setup, evidence and mutation tools |
| `ci/` | Inventory policy, generated dependency plan and pinned tool dependencies |
| `.github/` | Shared actions and workflows |
| `tests/` | Tool regressions and small immutable fixtures |
| `release-profiles/` | Historical verification inputs; not a current support matrix |

Generated evidence lives outside source checkouts. See [artifact
storage](docs/ARTIFACT-STORAGE.md) for retention and recovery, and
[visibility policy](VISIBILITY.md) for what belongs in a public contribution.
