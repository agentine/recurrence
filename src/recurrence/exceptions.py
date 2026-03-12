"""Exception hierarchy for recurrence (schedule-compatible)."""


class ScheduleError(Exception):
    """Base exception for all scheduling errors."""


class ScheduleValueError(ScheduleError):
    """Raised when an invalid value is provided to a scheduling method."""


class IntervalError(ScheduleValueError):
    """Raised when an invalid interval is specified."""
