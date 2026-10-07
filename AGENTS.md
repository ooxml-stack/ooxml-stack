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

- Write public-facing documentation and contributor instructions in English.

- This public repository contains coordination documentation and shared engineering
  tooling. Use `docs/ARCHITECTURE.md` for ownership and `docs/README.md` for navigation.
- Apply `VISIBILITY.md` to source and documentation changes. Public tooling and
  pinned dependency identities do not authorize publishing private runtime code
  or evidence. Preserve existing caller paths when organizing documentation.
- Keep historical results attached to their original identities. Follow the
  current artifact-storage policy when interpreting historical file paths.

## Public commit identity

- Use the GitHub privacy identity `iamtouchskyer
  <14212314+iamtouchskyer@users.noreply.github.com>` for the repository owner's
  author and committer fields. Never use a personal email address.
- Before committing or pushing, verify author, committer and tagger identities,
  commit-message trailers, and newly added content. Use noreply addresses for
  attribution; do not replace other contributors' identities without permission.
- Set this identity in repository-local Git configuration. Do not rely on a
  global configuration that may expose a personal address.
- After a privacy history rewrite, use the rewritten history. Do not merge or
  force-push old refs back into public branches or tags. Keep recovery bundles
  private and migrate live commit pins using the recorded identity mapping.
- GitHub merge and squash commits also need an explicit private author email:
  pass `--author-email 14212314+iamtouchskyer@users.noreply.github.com` to
  `gh pr merge`, then inspect the resulting author and committer. Repository-local
  Git configuration does not control commits created by GitHub.
