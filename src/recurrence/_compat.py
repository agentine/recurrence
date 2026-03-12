"""Compatibility shim for ``import recurrence as schedule`` migration.

This module re-exports the full public API so that code written against
the ``schedule`` library can switch to ``recurrence`` with a one-line
import change::

    # Before
    import schedule

    # After
    import recurrence as schedule
"""

from recurrence.exceptions import (  # noqa: F401
    ScheduleError,
    ScheduleValueError,
    IntervalError,
)
from recurrence.scheduler import (  # noqa: F401
    Job,
    Scheduler,
    default_scheduler,
    every,
    run_pending,
    run_all,
    get_jobs,
    clear,
    cancel_job,
    next_run,
    idle_seconds,
    repeat,
)

# These are defined in __init__.py — import from there.
from recurrence import CancelJob, jobs  # noqa: F401

__all__ = [
    "CancelJob",
    "Job",
    "Scheduler",
    "ScheduleError",
    "ScheduleValueError",
    "IntervalError",
    "default_scheduler",
    "every",
    "run_pending",
    "run_all",
    "get_jobs",
    "clear",
    "cancel_job",
    "next_run",
    "idle_seconds",
    "repeat",
    "jobs",
]
