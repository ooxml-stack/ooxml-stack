"""Turn a catchable termination signal into the runner's controlled interrupt.

Python's default SIGTERM handler terminates the process outright: no exception
is raised, no ``finally`` runs and no ``atexit`` hook is called. A run stopped
by a task manager therefore left its report at ``running`` forever and never
removed its container. SIGINT already worked because it raises
``KeyboardInterrupt``.

This module gives SIGTERM and SIGHUP the same treatment for the duration of one
host-side run, and restores whatever handlers were installed before.
"""

from __future__ import annotations

import contextlib
import signal

# Signals a task manager or a shell sends to ask a process to stop. They are
# catchable, unlike SIGKILL.
TERMINATION_SIGNALS = (signal.SIGTERM, signal.SIGHUP)


class TerminationRequested(KeyboardInterrupt):
    """A catchable stop signal arrived and the run has been finalized.

    It subclasses ``KeyboardInterrupt`` so every existing ``except
    BaseException`` finalization path treats it exactly like Ctrl-C, while still
    naming the signal that asked for the stop.
    """

    def __init__(self, signum: int):
        super().__init__(f"terminated by signal {signum}")
        self.signum = signum


@contextlib.contextmanager
def termination_as_interrupt():
    """Route a catchable termination signal into the Ctrl-C path.

    Raising puts the signal on the path that already finalizes the report and
    removes the container. The previous handlers are restored on the way out, so
    a library caller is not left with the runner's policy installed.
    """
    def handler(signum, frame):
        raise TerminationRequested(signum)

    installed = {}
    for signum in TERMINATION_SIGNALS:
        try:
            installed[signum] = signal.signal(signum, handler)
        except (ValueError, OSError, AttributeError):
            continue  # not the main thread, or the signal does not exist here
    try:
        yield
    finally:
        for signum, previous in installed.items():
            signal.signal(signum, previous)