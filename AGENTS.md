# ooxml-stack Agent Notes

## Workspace Instructions

- Shared workspace rules live in `docs/WORKSPACE-AGENTS.md`. Install the root
  entry with `make workspace-init WORKSPACE=/path/to/ooxml-projects`; see
  `docs/DEVELOPER-WORKTREES.md`. Keep repository-specific rules in this file.

## Developer Worktrees

- Create development checkouts with `python3 -m scripts.dev_worktree` or
  `make worktree`; see `docs/DEVELOPER-WORKTREES.md` for arguments and closeout.
- The entry confines checkouts to `.worktrees/<task>/<repository>` and records
  ownership and retirement conditions. Preserve failed/interrupted records for
  inspection; runtime snapshots retain their own existing lifecycle contracts.

## Capability Claims

- Read `docs/CAPABILITY-CLAIMS.md` before making OOXML
  compatibility, readability, editability, or full-write claims.
- Use capability names and measured denominators in user-facing docs. Do not use
  internal phase IDs as public claim language.
- Store all generated evidence outside source checkouts; see
  `docs/ARTIFACT-STORAGE.md`. Historical paths are provenance references only.
- Retain immutable regression inputs under `tests/fixtures/` only when consumed
  by tests. Do not promote generated campaigns back into the source tree.
- Preserve external evidence, original failure outcomes, manifests, hashes and
  Git/LFS recovery data. Release bundles are delivered as external artifacts.

## Repository Scope

- This public repository contains coordination documentation and shared engineering
  tooling. Use `docs/ARCHITECTURE.md` for ownership and `docs/README.md` for navigation.
- Apply `VISIBILITY.md` to source and documentation changes. Public tooling and
  pinned dependency identities do not authorize publishing private runtime code
  or evidence. Preserve existing caller paths when organizing documentation.
- Keep historical results attached to their original identities. Follow the
  current artifact-storage policy when interpreting historical file paths.
