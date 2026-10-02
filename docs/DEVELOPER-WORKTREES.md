# Developer worktrees

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
