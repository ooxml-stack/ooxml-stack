# Architecture and repository ownership

The product serves agents that need to read, analyze, edit and audit Office
files. CLI, MCP, HTTP and client integrations should share operation identities,
object addresses, result schemas, errors and evidence semantics.

These are ownership boundaries, not a claim that every operation is implemented
for every format or exposed by every interface. Consult the selected runtime
release and [capability evidence](CAPABILITY-CLAIMS.md).

## Repository map

| Repository | Owns |
| --- | --- |
| `ooxml-operation-engine` | Office operation contracts, execution, validation, structured evidence and CLI/MCP adapters |
| `ooxml-apps` | HTTP gateway, document revisions, candidate review and workbench UI |
| `python-docx` | DOCX-specific object model and read/write behavior |
| `python-pptx` | PPTX-specific object model and read/write behavior |
| `python-xlsx` | XLSX-specific object model and read/write behavior |
| `ooxml-core` | Shared DrawingML and package infrastructure |
| `ooxml-spec` | Schema data, specification queries and generation inputs |
| `ooxml-stubs` | Generated XML element support and registration |
| `ooxml-test-framework` | Reusable validation rules, preservation checks and test harnesses |
| `ooxml-native-corpus` | Private native-document corpus, provenance and baselines |
| `ooxml-stack` | Shared engineering tools, dependency plans and project contracts |

Names identify responsibilities. They do not indicate public access or license
rights; repository access and distributed component licenses are separate facts.

## Execution and application state

The Engine is the authority for document operations. Apps adapts it and owns
application state such as revision history and review decisions. An Apps
candidate is bound to an explicit document revision; gateway/UI code should not
introduce a second implementation of Office object mutation.

Format libraries own format-specific semantics. Shared implementation belongs in
Core when consumers can use the same behavior. Schema knowledge and generated
XML classes support those libraries; class or tag counts are not counts of
agent-editable features.

Engine runtime validation currently consumes rules from Test Framework. The
validation library and its test harness have different consumers even though
they share a repository. Preserve runtime validation when changing packaging;
do not introduce a runtime dependency on private corpora or model evaluators.

The inventory [policy](../ci/ecosystem-policy.json) and generated
[plan](../ci/ecosystem-plan.json) describe the engineering dependency graph.
This ownership map does not replace their pinned source identities or refresh
that graph. The plan is a derived baseline, not a live query of GitHub visibility,
installed versions or the latest supported product release.

## Three execution tools with different purposes

| Component | Executes | Evidence |
| --- | --- | --- |
| Operation Engine | A user's Office operations | Results, artifacts, validation and change evidence |
| TaskBench, maintained with Engine | Controlled agent-task evaluations | Frozen task/model conditions, attempts and independent scoring |
| Shared runner in this repository | Repository verification through adapters | Commit, runner and plan identity plus stage results |

Product audit concerns a particular document and change. TaskBench evaluates
agent behavior. Shared-runner success proves its declared check scope. None is a
substitute for the other two, and model requests need an authorized plan and
budget.

## Distribution and publication

Runtime packages, Apps releases and shared engineering tooling have separate
installation requirements. An agent should consume a runtime distribution or
service; it should not need to reconstruct the entire development workspace.
Rendering and native Office checks retain their declared provider requirements.

This repository publishes coordination documentation and shared tooling. Its
public status does not open another repository, provide runtime installation
rights, or select a commercial or open-source license for the product.

The [client distribution plan](PUBLIC-CLIENT-BOUNDARY.md) separates the proposed
public SDK/CLI from private execution and describes the release sequence. It is
a planned boundary, not an announcement of client or service availability.
