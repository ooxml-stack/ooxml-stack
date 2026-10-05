# Artifact storage

Generated run evidence belongs outside source checkouts, even when it is private
or ignored by Git. Do not create repository-local `evidence/`, `release-evidence/`,
`docs/evidence/`, or `.uxe/evidence/` directories or compatibility symlinks.

Set `OOXML_ARTIFACT_ROOT` to a durable external directory. The default in the
OOXML workspace is `.delivery-evidence/artifacts/`; standalone clones and installed
packages default to `~/.local/share/ooxml/artifacts/`. Tools append the repository
name and area (`evidence`, `release-evidence`, `uxe`, or `workbench`). Existing
explicit CLI output arguments remain available; choose an external directory.
A configured default located inside a Git checkout is rejected.

Historical artifacts retain their original bytes, outcomes, source identities,
and timestamps. Moving evidence does not constitute a new verification run.
`ARTIFACT-ARCHIVE-INDEX.json`, where present, records formerly tracked paths,
content SHA-256, sizes, modes, and the source commit. The corresponding external
location is `<artifact root>/<repository>/<original path>`. Local-only artifacts
have a separate migration inventory under the workspace delivery records.

On another machine, copy the external store separately and verify its inventory.
Git clones do not download local evidence. Formerly tracked artifacts can also be
restored from the index's source commit into an external staging directory using
`git archive <source_commit> evidence release-evidence` with only the areas present
in that repository. Hydrate Git LFS payloads from the retained LFS store as needed;
a pointer file is not the original artifact. No history or LFS objects were pruned.

Historical documents and locked profiles may quote the original paths. Those are
provenance references, not instructions to recreate evidence inside the checkout.
Regenerate or replay only with explicit external inputs/outputs. Missing evidence
remains missing; readers must not convert absence into a successful empty run.

Small immutable inputs actually consumed by regression tests live in
`tests/fixtures/`, with their original content hashes. They test evidence readers
and refusal cases; they do not certify the current runtime or a release. Runtime
package resources under `src/.../evidence/` are shipped contract inputs, not local
run output, and retain their existing ownership.

For a historical release profile, bind a disposable external copy before running
the existing core verifier. Expected metrics, hashes, and sizes remain unchanged:

```bash
export OOXML_ARTIFACT_ROOT=/path/to/external/artifacts
python scripts/materialize_release_profile.py release-profiles/p51-ooxml-semantic-compatibility-1.locked.json --output /path/to/external/p51-profile.json
python ../ooxml-core/scripts/verify_release_profile.py --profile /path/to/external/p51-profile.json
```

The core verifier still rejects missing or mismatched artifacts. This binding step
does not run Office, models, or the release verifier. The redaction utility now
requires `--root /external/export`; use a disposable export, since redaction
changes content and optionally refreshes its own locks.
