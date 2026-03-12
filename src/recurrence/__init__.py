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


__all__ = [
    "CancelJob",
    "ScheduleError",
    "ScheduleValueError",
    "IntervalError",
]
