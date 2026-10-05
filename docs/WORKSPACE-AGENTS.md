# Workspace directory layout

This directory contains the canonical OOXML repositories and shared local artifacts.
Follow the parent and each repository's own AGENTS.md for coding and Git rules.

- Keep canonical repositories at the workspace root.
- Create new developer worktrees and independent checkouts under
  `.worktrees/<task>/<repository>`.
- Use ooxml-stack's `python3 -m scripts.dev_worktree` entry for developer worktrees;
  see its `docs/DEVELOPER-WORKTREES.md`. Runtime temporary directories and retained
  TaskBench campaign snapshots follow their existing lifecycle contracts.
- Write experiment outputs and delivery evidence under
  `.delivery-evidence/<task>`. Shared artifact storage uses
  `.delivery-evidence/artifacts/<repository>/`; set `OOXML_ARTIFACT_ROOT` to
  override it. Generated evidence must not live inside any source checkout,
  even in a Git-ignored directory. See `docs/ARTIFACT-STORAGE.md` in ooxml-stack.
- Keep retired evidence, cleanup inventories, and recovery archives under
  `.archive-backups/`.
- Reuse these containers instead of creating new task directories at the root.
- Preserve active worktrees and their existing paths until their tasks finish.

## Task lifecycle

- When creating a task workspace, record its task/owner, checkout paths, evidence
  location, and retirement condition in the existing task record or handoff.
- Include evidence placement and workspace disposition in task closeout. Within
  the authorized scope, retire disposable workspaces after verification; record
  a concrete reason and next action for each retained workspace.
- Keep shared rules here and repository-specific rules in the owning repository.
  Keep current counts and task statuses in evidence records, not these rules.

## Safe retirement

- Decide from current contents and dependencies. Names, age, a clean Git status,
  or a merged branch alone do not establish that a directory is disposable.
- Check modified, untracked and ignored files; HEAD, refs and reflog tips; Git
  common directories, alternates and dependent worktrees; process/open-file use;
  symlinks, editable installs, and references from active scripts and evidence.
- Preserve unique changes and active dependency chains. Distinguish historical
  inventory references from dependencies still needed to run or replay work.
- Immediately before deletion, recheck changes and process use. Defer changed or
  active candidates and their dependencies, recording the observed reason.
- Preserve other developers' work. Remove registered worktrees with
  `git worktree remove`; do not force removal to get past local changes.
- After cleanup, verify removed paths and registrations, and compare protected
  repositories/worktrees against their pre-cleanup snapshots. Record concurrent
  changes without attributing them to cleanup or reverting them.

## Recovery proof

- Before deletion, retain unique Git history and required LFS objects; archive
  evidence and local files with original relative paths and a recovery manifest.
- Verify archived members against their source hashes, permissions and symlink
  targets. Verify unique history is reachable in a retained repository or bundle.
- Test recovery bundles in a fresh repository with their declared prerequisites;
  record whether each bundle is standalone or requires existing history.
- Document how to recreate the checkout from its recorded Git identity before
  restoring files. Exclude archived `.git` pointer files during restoration;
  preserve the new checkout's Git metadata and document path dependencies.

## Verification and reporting

- Project tests run on the user-authorized LAN host unless the user authorizes
  another environment. Local filesystem, Git, archive and document checks are
  sufficient for cleanup or documentation-only changes; label them accurately.
- Record tested commit, environment, scope and evidence paths. Keep preparation,
  actual execution, framework acceptance and model business success distinct.
  Local or LAN results do not establish that GitHub Actions ran successfully.
- Derive counts from source reports/manifests. Reconcile totals and unions with
  their scope and timestamp, including concurrent additions or removals.
- Report a disposition for every item in the authorized cleanup scope: removed,
  archived, retained with a reason, or blocked. A lower directory count alone
  does not establish completion; refresh retained reasons before later cleanup.
- Do not infer reclaimed physical disk space by summing `du` output; hardlinks,
  filesystem sharing and concurrent work can invalidate that estimate.
- Model requests require an explicitly authorized plan and budget. Offline
  analysis, cleanup and report regeneration do not authorize model execution.
