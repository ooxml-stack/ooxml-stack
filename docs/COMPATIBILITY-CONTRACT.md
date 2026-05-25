# OOXML Compatibility Contract

This contract defines what the OOXML Stack may claim about DOCX/PPTX I/O
compatibility. It is intentionally narrower than "100% Office compatible".

## Supported-Valid Files

A file is supported-valid when all of these are true:

- The container is a readable ZIP OPC package.
- `[Content_Types].xml` is present, well-formed, and covers package parts.
- XML parts required for open are well-formed XML.
- Internal relationships do not require missing mandatory parts.
- The file is not encrypted or password protected.
- The package format is DOCX or PPTX, including Transitional and Strict OOXML.

Files outside this set must be classified, not counted as normal compatibility
bugs. Excluded categories include encrypted CFB containers, empty files,
corrupt ZIP members, malformed XML, missing OPC content types, and non-OOXML
packages saved with an OOXML extension.

## Required Guarantees

For supported-valid files, readiness claims require machine evidence for:

- Open succeeds without an uncaught exception.
- Passive open-save roundtrip produces a readable OPC package.
- Active edit-save-reopen roundtrip succeeds for opened files.
- No missing parts, relationship loss, or binary mutation is introduced.
- Exact preserve and compatible preserve are reported separately.
- Office open gates report zero repair dialogs for the release corpus.
- Schema validation reports zero errors for generated release artifacts.
- Fresh install from release tags passes smoke validation.

## Preserve Semantics

Exact preserve means byte-level package invariants pass. Compatible preserve is a
separate metric for documented equivalence classes, such as valid synthesis of
missing content-type declarations for otherwise byte-preserved opaque parts.

Compatible preserve must never hide exact differences. Each accepted equivalence
class needs a named machine classification and a regression test.

## Non-Goals

This contract does not claim:

- Byte-identical ZIP container metadata after save.
- Preservation of encrypted container bytes after decrypt/process/re-encrypt.
- Digital signature validity after modifying or rewriting a package.
- Full visual/rendering parity unless a specific render gate proves it.
- Support for corrupt, malformed, mislabeled, or non-OOXML inputs.

## Public Claim Rule

Do not claim "100% Office compatible" unless every guarantee above has current
evidence and every excluded file is machine-classified. Prefer scoped language:
"100% open and active roundtrip for supported-valid files in the measured
corpus," followed by exact preserve, compatible preserve, and exclusion counts.
