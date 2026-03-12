"""Compatibility shim for ``import recurrence as schedule`` migration."""

from recurrence.exceptions import (
    ScheduleError,
    ScheduleValueError,
    IntervalError,
)

__all__ = ["ScheduleError", "ScheduleValueError", "IntervalError"]
