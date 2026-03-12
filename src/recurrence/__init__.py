"""recurrence — A zero-dependency, modern Python replacement for schedule."""

__version__ = "0.1.0"

from recurrence.exceptions import (
    ScheduleError,
    ScheduleValueError,
    IntervalError,
)


class CancelJob:
    """Sentinel: return from a job function to cancel it.

    Returning ``CancelJob`` or ``CancelJob()`` from a job function
    removes the job from the scheduler after the current run.
    """
    pass


# Import after CancelJob is defined (scheduler.py imports CancelJob).
from recurrence.scheduler import (  # noqa: E402
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

# Expose jobs list directly (schedule compatibility).
jobs = default_scheduler.jobs

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
