"""Host-side container launch.

The runner mounts three read-only inputs - the commit snapshot, the pinned
runner checkout, and the plan file - plus a writable reports directory, and
starts the container bootstrap. Everything is passed as an argv element, so a
path containing spaces or shell metacharacters survives unchanged and is never
interpreted by a shell.
"""

from __future__ import annotations

import base64
import os
import subprocess
import threading
from pathlib import Path

CONTAINER_WORKSPACE = "/workspace"
CONTAINER_INPUT = "/input"
CONTAINER_REPORTS = "/reports"
CONTAINER_RUNNER = "/runner"
CONTAINER_PLAN = "/plan"
DOWNLOAD_CACHE_VOLUME = "ooxml-ci-downloads-v1"
MAX_CPUS = 4

# The platform partition names the engine adapter understands. The runner only
# decides whether to forward the selection; the adapter still refuses a bucket
# that is not in that repository's own allocation, and a name the runner does
# not know is refused on the host before a container starts.
PLATFORM_BUCKETS = frozenset({"default", "macos", "dsh-runtime"})


class DockerError(RuntimeError):
    """Docker could not be queried or the container could not be started."""


def cpu_limit() -> int:
    result = subprocess.run(
        ["docker", "info", "--format", "{{.NCPU}}"], capture_output=True, text=True, check=True, timeout=30
    )
    try:
        available = int(result.stdout.strip())
    except ValueError as exc:
        raise ValueError(f"docker reported an unusable CPU count: {result.stdout!r}") from exc
    if available < 1:
        raise ValueError("Docker reported no available CPUs")
    return min(MAX_CPUS, available)


def _mounts(workspace: Path, reports: Path, runner_root: Path, plan: Path) -> list[str]:
    pairs = (
        (workspace, CONTAINER_INPUT, ",readonly"),
        (reports, CONTAINER_REPORTS, ""),
        (runner_root, CONTAINER_RUNNER, ",readonly"),
        (plan, CONTAINER_PLAN, ",readonly"),
    )
    argv: list[str] = []
    for source, target, mode in pairs:
        argv += ["--mount", f"type=bind,source={source},target={target}{mode}"]
    return argv


def platform_bucket(environ=None):
    """The partition this run owns, when the caller selected one.

    The engine's adapter reads this in the container to select the node IDs one
    platform owes. A whitelisted value is forwarded verbatim; an unknown value
    fails here, before a container starts, rather than silently unpartitioned.
    """
    value = (os.environ if environ is None else environ).get("OOXML_PLATFORM_BUCKET")
    if not value:
        return None
    if value not in PLATFORM_BUCKETS:
        raise DockerError(f"unknown OOXML_PLATFORM_BUCKET {value!r}; expected one of {sorted(PLATFORM_BUCKETS)}")
    return value


def _env(config: dict, commit: str, runner_commit: str, name: str, cpus: int) -> list[str]:
    values = {
        "PYTHONPATH": CONTAINER_RUNNER,
        # The adapter reaches the runner through its own repository's bridge, so
        # the mount point has to be named explicitly. Without this the bridge
        # would look for a sibling checkout that does not exist in the container.
        "OOXML_RUNNER_ROOT": CONTAINER_RUNNER,
        "UV_CACHE_DIR": "/cache/uv",
        "PYTHONUNBUFFERED": "1",
        "TZ": "UTC",
        "LANG": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        "OOXML_CI_COMMIT": commit,
        # The container re-derives the runner's own identity from the mount and
        # refuses to run when it is not this commit's source.
        "OOXML_CI_RUNNER_COMMIT": runner_commit,
        "OOXML_CI_IMAGE": config["image"],
        "OOXML_CI_RUN_ID": name,
        "OOXML_CI_REPORT_UID": str(os.getuid()),
        "OOXML_CI_REPORT_GID": str(os.getgid()),
        "OOXML_CI_CPUS": str(cpus),
        # The runner is a bind mount owned by whoever checked it out on the host,
        # which the container's root user is not, and Git refuses to read such a
        # repository. It is trusted by construction: it is the pinned checkout
        # this run was launched against. The workspace needs no entry because the
        # container materializes its own copy as root.
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": CONTAINER_RUNNER,
    }
    selected = platform_bucket()
    if selected:
        values["OOXML_PLATFORM_BUCKET"] = selected
    return [item for key, value in values.items() for item in ("--env", f"{key}={value}")]


def command(
    *, workspace: Path, reports: Path, runner_root: Path, plan: Path, config: dict,
    commit: str, runner_commit: str, name: str, cpus: int, repository: str, adapter: str,
) -> list[str]:
    """Build the ``docker run`` argv for one execution."""
    argv = [
        "docker", "run", "--rm", "--init", "--name", name,
        "--platform", config["platform"],
        "--workdir", f"{CONTAINER_WORKSPACE}/{repository}",
        "--interactive", "--cpus", str(cpus), "--memory", "8g",
        *_mounts(Path(workspace), Path(reports), Path(runner_root), Path(plan)),
        "--mount", f"type=volume,source={DOWNLOAD_CACHE_VOLUME},target=/cache",
        *_env(config, commit, runner_commit, name, cpus),
        config["image"], "python", "-m", "ooxml_runner.bootstrap",
        "--repository", repository, "--adapter", adapter,
    ]
    return argv


def _copy_log(stream, destination: Path, token: str) -> None:
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    with destination.open("w", encoding="utf-8") as output:
        for line in stream:
            clean = line.replace(token, "***").replace(encoded, "***")
            output.write(clean)
            output.flush()
            print(clean, end="", flush=True)


def _hand_over_token(process: subprocess.Popen, token: str) -> None:
    """Write the token to the child's stdin, tolerating a child that exits first.

    A container that dies before it reads stdin - an unstartable image, a
    missing mount, a stub in a test - closes the pipe. The child's exit status
    is the result the caller needs, so a broken pipe here must not replace it
    with a less specific error.
    """
    try:
        process.stdin.write(token + "\n")
    except OSError:
        pass
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass


def _cleanup(name: str) -> None:
    """Best-effort removal of this run's container.

    Cleanup must never replace the result the run already produced: a missing
    Docker CLI or a slow daemon is not the failure the caller needs to see.
    """
    try:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def execute(argv: list[str], reports: Path, token: str, timeout: float, name: str) -> int:
    """Run the container, streaming its log live, and always clean the container up."""
    process = subprocess.Popen(
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    reader = threading.Thread(
        target=_copy_log, args=(process.stdout, Path(reports) / "run.log", token), daemon=True
    )
    reader.start()
    try:
        _hand_over_token(process, token)
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _cleanup(name)
        process.kill()
        process.wait()
        raise
    finally:
        if process.poll() is None:
            _cleanup(name)
            process.kill()
            process.wait()
        reader.join(timeout=30)