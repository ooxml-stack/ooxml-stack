# Public clients and runtime distribution

This document records the selected local distribution model and implementation
sequence. The public [OOXML Client](https://github.com/ooxml-stack/ooxml-client)
contains a Python SDK, CLI and MCP launcher. It does not include an Engine or
announce a commercial runtime release. The Engine remains the owner of Office
execution; clients adapt its supported external contracts.

## Selected delivery model

Publish the CLI and SDK as an independent open-source client. Supply the Engine
as a separately installed runtime under the applicable commercial distribution
terms. Office processing runs on the user's machine or server; a hosted OOXML
service is not required. Agents and external providers retain their own data
flows, which must be described separately.

The client and runtime are separate packages and separate license scopes.
Existing upstream rights and previously granted licenses remain intact. The
commercial release requires a completed component and distribution review; this
decision does not retroactively relicense existing code.

A customer receives executable runtime code for local use. This model relies on
a clear license and supported distribution, not a promise that the delivered
program cannot be inspected or copied. Cloud-only execution is not the default
product architecture.

## Publication boundary

| Component | Intended scope |
| --- | --- |
| Stack | Public documentation, capability contracts and shared engineering tools |
| `ooxml-client` | MIT-licensed Python SDK, lightweight CLI, MCP launcher and examples |
| Engine | Private execution implementation, with separately defined distribution terms |
| Apps | Private full application and service; reusable client examples belong with the clients |
| Format libraries and Core | Keep the enhanced implementation private; review general fixes for upstream contribution |
| Spec | Candidate for an independent open-source release after data and license review |
| Stubs | Keep with its implementation dependencies until independently useful |
| Test Framework | Keep the complete implementation private; extract narrowly scoped public evidence checks |
| Native Corpus | Private source documents and baselines; create separately reviewed public examples |

These are access and product boundaries, not changes to existing licenses.
Existing upstream notices and permissions must be preserved. Audit actual
previous distributions and their terms before choosing terms for a new release;
changing repository visibility does not revoke previously granted rights.

## Client and runtime are separate artifacts

The current Engine CLI and Python SDK execute Engine code in-process. The
Engine wheel includes that implementation and references private dependencies.
Publishing them would publish runtime implementation. The independent
`ooxml-client` package instead uses the public MCP SDK to connect to a separately
installed runtime; its package dependencies do not include private Office code.

The public client contains argument handling, MCP transport, result presentation
and examples. Office parsing, mutation, preservation and runtime validation remain in
the Engine. Installing the client must not install private Engine source or
require access to the organization's private Git repositories.

| Distribution | What reaches the user's machine | Consequence |
| --- | --- | --- |
| Public client with hosted Engine | Client code and returned results | Engine implementation remains on the service |
| Public client with licensed local Engine | Client plus separately distributed runtime | Users possess the executable; source confidentiality cannot be guaranteed |
| Current Python Engine wheel | Engine Python implementation | Publishing this wheel exposes implementation files even if its repository is private |

A commercial license and source confidentiality are different properties.
Compilation or bundling does not establish that a locally distributed runtime
cannot be inspected or reverse-engineered. A local runtime must have explicit
installation and license terms rather than silently pulling private Git sources.
A hosted path must define document transfer and retention behavior before use.

## Forks and service access

An open-source client can be modified, redistributed and connected to another
implementation under its applicable license. That does not grant rights to
private Engine code or free access to a hosted service. Product value remains in
the Engine's demonstrated behavior, its maintenance and the service offered.

A hosted service must enforce authentication, per-user authorization and usage
limits itself. Client-side checks cannot enforce billing or access, because the
client can be changed or replaced. Never embed a shared service secret in a
client. Credentials must be scoped to the configured service and must not leak
through logs or transfers to unrelated endpoints.

Official package ownership, release provenance and clear installation instructions
help users distinguish maintained releases from modified distributions. Publishing
client code alone neither provides these controls nor proves them effective.

## Delivery sequence

1. **Record the boundary and license basis.** Identify each proposed public
   artifact, its owner, dependencies and existing rights. Keep the license audit
   and operational history outside public source. This document records the
   boundary; the distribution and license review remains release work.
2. **Establish a usable runtime connection.** Verify the selected local
   distribution path with client and Engine installed separately. Version the external requests,
   results, capability discovery and error behavior against a runtime release.
   A clean consumer environment must not need a private source checkout.
3. **Ship one independent client repository.** Keep SDK, CLI and agent examples
   together initially. Reuse external contracts without copying Engine execution
   code. Check built artifacts and their dependency closure, including source
   distributions, so private implementation is not published transitively.
4. **Verify real user workflows.** Exercise supported DOCX, PPTX and XLSX cases
   through the client and real runtime. Record input/output identities, intended
   changes, errors and unavailable checks. Test credential boundaries and failure
   paths. Local execution must not require an OOXML cloud connection. Public
   examples must have their own redistribution rights.
5. **Publish the verified release and complete migration.** Provide installation,
   version compatibility, licenses, support boundaries and release evidence.
   Finish English documentation and the scoped history cleanup after protecting
   recovery data and migrating consumers pinned to rewritten Stack identities.
   Record old/new commit mappings; historical test results keep their original
   identities. Account separately for retained tags, PR references and copies
   outside the repository owner's control.

Each step has its own evidence. A document or mock-client test does not establish
that an external developer can run the real product. A public checksum verifier
can establish artifact identity; it cannot establish semantic or visual fidelity
without the relevant checks. Apply the [capability-claim rules](CAPABILITY-CLAIMS.md)
to release descriptions and examples.

An independent Spec release can follow its own review. It is not a prerequisite
for the client distribution.
