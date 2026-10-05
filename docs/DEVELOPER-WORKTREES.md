# Developer worktrees

## Initialize a workspace

Place the canonical repositories side by side, with this repository named
`ooxml-stack`. From that checkout, run:

```sh
make workspace-init WORKSPACE=/path/to/ooxml-projects
# Equivalent, using only the Python standard library:
python3 -m scripts.workspace_agents --workspace /path/to/ooxml-projects
```

This installs `AGENTS.md -> ooxml-stack/docs/WORKSPACE-AGENTS.md` at the workspace
root. The shared rules are tracked in Git; the root link is installed locally.
Run this once on each machine after obtaining a stack revision containing the
installer. Cloning a repository alone does not create a file in its parent.
The relative link survives moving the entire workspace and reads subsequent
updates from the canonical stack checkout. Even when invoked from a task
worktree, the installer uses the canonical source under the requested workspace.

Rerunning with the correct link is harmless. Missing or symlinked canonical
sources are refused. An existing file, directory or different link is preserved
and causes a nonzero exit. Before migrating an existing root `AGENTS.md`, compare
it with the tracked rules, retain any unique instructions, archive it with its
permissions and hash, then remove only that reviewed entry and rerun the command.
If installation fails, restore the original entry from the archive. The installer
does not overwrite, merge or delete existing instructions.

Edit shared rules in `docs/WORKSPACE-AGENTS.md` through normal Git review. Keep
repository-specific instructions in each repository's own `AGENTS.md`. Parent
agent configuration remains local unless separately managed.

## Create a task checkout

From an ooxml-stack checkout, create a task checkout with:

```sh
python3 -m scripts.dev_worktree \
  --workspace /path/to/ooxml-projects \
  --task my-fix --repository ooxml-operation-engine \
  --owner developer --retire-when 'Merged and evidence retained' \
  --branch my-fix
```

The command creates `.worktrees/my-fix/ooxml-operation-engine` and an adjacent
`ooxml-operation-engine.worktree.json`. The record binds the source commit,
owner, evidence location and retirement condition. Without `--branch`, the new
worktree is detached. The source checkout may contain other developers' changes;
only its committed revision is used and those local changes are preserved.

`make worktree WORKSPACE=... TASK=... REPOSITORY=... OWNER=... RETIRE_WHEN=...`
creates a detached checkout; `REVISION` defaults to `HEAD`.

Names containing path separators, symlinked paths, existing destinations
(including empty directories), and existing records are refused. Creation
failures retain a `failed` or `interrupted` record for inspection. An uncatchable
termination may leave `preparing`; inspect it before retrying. The command never
removes a pre-existing checkout or cleans up a failed checkout automatically.

At closeout, retain evidence under `.delivery-evidence/<task>`, verify unique
changes/history and active dependencies, then remove disposable checkouts with
`git worktree remove`. Keep unresolved work and its concrete retention reason in
the task handoff. This is the developer creation entry, not a replacement for
runner `TemporaryDirectory` snapshots or retained TaskBench campaign snapshots.

`make runner-test` exercises the command using temporary Git repositories,
including rejected paths, preserved source edits, failures and interruption.
It also tests workspace initialization, local-rule preservation and relocation.
