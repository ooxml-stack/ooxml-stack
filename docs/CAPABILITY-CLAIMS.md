# Capability claims

Describe a capability by format, operation, supported objects, interface and
runtime version. A schema entry, generated class, passing unit test or historical
release profile does not establish end-to-end support.

This guide replaces the missing public capability-ledger reference. It is not a
live operation inventory or a new set of compatibility measurements. The selected
runtime's capability discovery and operation schemas define what it exposes;
version-bound validation evidence establishes what has actually been verified.

## Describe the behavior being measured

| Capability | What the evidence must distinguish |
| --- | --- |
| Preserve | Retained parts, relationships, unknown content and binary data; exact and compatible preservation reported separately |
| Detect | Recognition of an object or feature |
| Inspect | Correct properties, values, types, scope and usable object addresses |
| Mutate | Requested changes plus preservation of non-target content after save and reopen |
| Create | Valid new objects with their required package relationships and dependencies |
| Validate | Which structural, semantic, rendering or native-application checks ran and what they found |

Reading or preserving a feature does not establish that it can be edited or
created. Document analysis may combine structured facts, search and comparison;
business conclusions still require the caller's task-specific reasoning.

## Evidence required for a claim

Record the runtime/package identity, format and input scope, operation, output
identity, checks actually executed, provider/environment where relevant, and
unsupported or unavailable cases. Derive denominators from those records.
Separate failures, skips, exclusions and missing evidence from passes.

A document audit should let a caller determine what changed, what was checked
and what remains unknown. Missing readback, an unavailable renderer or an absent
native check must not be presented as successful validation.

A successful engineering check, a TaskBench framework acceptance and a model's
business-task success are different results. Repeated agent-task reliability
requires comparable attempts; a single pass is not a stability measurement.

## Compatibility scope

The [compatibility contract](COMPATIBILITY-CONTRACT.md) currently defines a
DOCX/PPTX supported-valid-file contract. Listing XLSX as a product format does not
extend that contract or establish Excel recalculation, visual parity or full
Office compatibility. Such claims require their own explicit scope and evidence.

Historical counts remain attached to their original revisions. Public summaries
may cite a reviewed, version-bound result, but must not turn schema coverage,
fixture counts or historical closeouts into an unqualified support guarantee.
