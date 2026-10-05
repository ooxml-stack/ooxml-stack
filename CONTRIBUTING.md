# Contributing

Contributions can improve project documentation or the shared engineering tools.
Use the [architecture](docs/ARCHITECTURE.md) to identify the owner of a change and
the [maintainer guide](docs/MAINTAINING.md) for this repository's entry points.

## Issues and examples

Describe the expected and observed behavior, component version, document format
and a minimal reproduction. Use a synthetic or redistributable example. Avoid
customer documents, credentials, local host details and raw private logs. A
private dependency's failure can be described here without copying its source
or granting access to it.

## Changes

- Keep one logical change per commit and preserve existing callers of shared
  runner, script and workflow entry points.
- Follow [AGENTS.md](AGENTS.md) and the shared workspace rules for worktrees,
  evidence placement and verification.
- Explain behavior changes and relevant validation. For documentation, check
  local links, referenced entry points and consistency with current code.
- For code changes, run the applicable tests in the designated test environment
  before committing and pushing. The [maintainer guide](docs/MAINTAINING.md)
  maps the suites; private dependency and native Office checks need their
  declared environments.
- Record the tested commit, environment and scope. A local or LAN result does
  not establish that GitHub Actions executed, or that a model task succeeded.
- Keep generated evidence outside source checkouts. Preserve original failure
  outcomes and recovery information.

## Public review

Follow [the public content policy](VISIBILITY.md). Check the provenance and
license of contributed code and fixtures. Do not add secret values, private
Office files, personal machine details or private runtime code.

Public capability statements follow [capability claims](docs/CAPABILITY-CLAIMS.md).
Historical reports, schema inventories and test counts are not a substitute for
current, scoped product evidence. This contribution guide does not grant or
change repository or dependency licenses.
