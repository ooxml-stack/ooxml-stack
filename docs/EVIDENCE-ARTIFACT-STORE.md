# Evidence blob storage

[Artifact storage](ARTIFACT-STORAGE.md) defines the current placement rule:
generated evidence lives outside source checkouts, including ignored output.
This page describes deduplication within that external store.

## External layout

An evidence area can contain structured JSON/JSONL records, validation results
and a content-addressed package store. For release evidence the layout is:

```text
<artifact root>/<repository>/release-evidence/
    <campaign>/...
    artifact-blobs/sha256/<aa>/<bb>/<sha>.<ext>
    artifact-blobs/artifact-manifest.jsonl
```

The record binds the artifact's hash, source identity and relevant result.
Preserve input/output bytes required to reproduce failures, release gates and
active verification. Hashes alone cannot recreate missing package bytes.

Deduplication must preserve the original relative-path mapping, bytes and
recovery instructions. Hardlinks are suitable only after all writers and native
Office checks have finished; subsequent writes would affect every linked path.
Logical sizes are not a measure of physical space reclaimed.

## Historical paths and cleanup

Older documents and profiles quote repository-local `release-evidence/` paths.
Those are provenance references. Use the archive index and recovery procedure
in [artifact storage](ARTIFACT-STORAGE.md) to locate or restore them externally.
The former repository-local allowlist is not an exception to the current rule.

`make evidence-hygiene` checks placement. It does not deduplicate files, verify
an archive's recovery, or authorize deleting evidence. Before cleanup, inspect
active dependencies and preserve unique files and required history under the
shared workspace rules. Retain manifests and verify recovery before removal.
