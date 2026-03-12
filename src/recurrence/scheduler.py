"""Core scheduler and job classes — 100% schedule-compatible API."""

from __future__ import annotations

import datetime
import functools
import random
import re
import time as _time
from typing import Any, Callable, Hashable, List, Optional, Set, Union

from recurrence import CancelJob
from recurrence.exceptions import IntervalError, ScheduleValueError


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

class Job:
    """A periodically-scheduled job, built via a fluent API."""

    def __init__(self, interval: int = 1, scheduler: Optional[Scheduler] = None) -> None:
        self.interval: int = interval
        self.latest: Optional[int] = None
        self.job_func: Optional[functools.partial[Any]] = None
        self.unit: Optional[str] = None
        self.at_time: Optional[datetime.time] = None
        self.at_time_zone: Any = None  # timezone info
        self.last_run: Optional[datetime.datetime] = None
        self.next_run: Optional[datetime.datetime] = None
        self.period: Optional[datetime.timedelta] = None
        self.start_day: Optional[str] = None
        self.cancel_after: Optional[datetime.datetime] = None
        self.tags: Set[Hashable] = set()
        self.scheduler: Optional[Scheduler] = scheduler

    def __repr__(self) -> str:
        if self.job_func:
            name = self.job_func.func.__name__
        else:
            name = "<unscheduled>"

        if self.at_time is not None:
            fmt_time = f" at {self.at_time}"
        else:
            fmt_time = ""

        if self.start_day is not None:
            return f"Every {self.interval} {self.unit} on {self.start_day}{fmt_time} do {name}()"
        return f"Every {self.interval} {self.unit or '?'}{fmt_time} do {name}()"

    def __lt__(self, other: Job) -> bool:
        return (self.next_run or datetime.datetime.max) < (
            other.next_run or datetime.datetime.max
        )

    # -----------------------------------------------------------------------
    # Time-unit properties (singular: interval must be 1)
    # -----------------------------------------------------------------------

    @property
    def second(self) -> Job:
        if self.interval != 1:
            raise IntervalError("Use .seconds instead of .second when interval > 1")
        return self.seconds

    @property
    def minute(self) -> Job:
        if self.interval != 1:
            raise IntervalError("Use .minutes instead of .minute when interval > 1")
        return self.minutes

    @property
    def hour(self) -> Job:
        if self.interval != 1:
            raise IntervalError("Use .hours instead of .hour when interval > 1")
        return self.hours

    @property
    def day(self) -> Job:
        if self.interval != 1:
            raise IntervalError("Use .days instead of .day when interval > 1")
        return self.days

    @property
    def week(self) -> Job:
        if self.interval != 1:
            raise IntervalError("Use .weeks instead of .week when interval > 1")
        return self.weeks

    # -----------------------------------------------------------------------
    # Time-unit properties (plural)
    # -----------------------------------------------------------------------

    @property
    def seconds(self) -> Job:
        self.unit = "seconds"
        return self

    @property
    def minutes(self) -> Job:
        self.unit = "minutes"
        return self

    @property
    def hours(self) -> Job:
        self.unit = "hours"
        return self

    @property
    def days(self) -> Job:
        self.unit = "days"
        return self

    @property
    def weeks(self) -> Job:
        self.unit = "weeks"
        return self

    # -----------------------------------------------------------------------
    # Weekday properties (interval must be 1)
    # -----------------------------------------------------------------------

    @property
    def monday(self) -> Job:
        if self.interval != 1:
            raise IntervalError("Weekday scheduling requires interval == 1")
        self.start_day = "monday"
        self.unit = "weeks"
        return self

    @property
    def tuesday(self) -> Job:
        if self.interval != 1:
            raise IntervalError("Weekday scheduling requires interval == 1")
        self.start_day = "tuesday"
        self.unit = "weeks"
        return self

    @property
    def wednesday(self) -> Job:
        if self.interval != 1:
            raise IntervalError("Weekday scheduling requires interval == 1")
        self.start_day = "wednesday"
        self.unit = "weeks"
        return self

    @property
    def thursday(self) -> Job:
        if self.interval != 1:
            raise IntervalError("Weekday scheduling requires interval == 1")
        self.start_day = "thursday"
        self.unit = "weeks"
        return self

    @property
    def friday(self) -> Job:
        if self.interval != 1:
            raise IntervalError("Weekday scheduling requires interval == 1")
        self.start_day = "friday"
        self.unit = "weeks"
        return self

    @property
    def saturday(self) -> Job:
        if self.interval != 1:
            raise IntervalError("Weekday scheduling requires interval == 1")
        self.start_day = "saturday"
        self.unit = "weeks"
        return self

    @property
    def sunday(self) -> Job:
        if self.interval != 1:
            raise IntervalError("Weekday scheduling requires interval == 1")
        self.start_day = "sunday"
        self.unit = "weeks"
        return self

    # -----------------------------------------------------------------------
    # Fluent methods
    # -----------------------------------------------------------------------

    def at(self, time_str: str, tz: Optional[str] = None) -> Job:
        """Schedule the job at a specific time.

        Format depends on unit:
        - day/weekday: ``"HH:MM"`` or ``"HH:MM:SS"``
        - hour: ``":MM"`` or ``"MM:SS"``
        - minute: ``":SS"``
        """
        # Validate that the unit is set.
        if self.unit not in ("hours", "days", "weeks", "minutes", "seconds"):
            raise ScheduleValueError(
                "at() is only valid for second/minute/hour/day/week units"
            )

        if tz is not None:
            try:
                from zoneinfo import ZoneInfo
            except ImportError:
                from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]
            self.at_time_zone = ZoneInfo(tz)

        # Parse time_str based on unit.
        if self.unit in ("days", "weeks"):
            # HH:MM or HH:MM:SS
            m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", time_str)
            if not m:
                raise ScheduleValueError(
                    f"Invalid time format {time_str!r} for {self.unit} unit. "
                    "Expected HH:MM or HH:MM:SS."
                )
            hour, minute = int(m.group(1)), int(m.group(2))
            second = int(m.group(3)) if m.group(3) else 0
            if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
                raise ScheduleValueError(
                    f"Invalid time values in {time_str!r}"
                )
            self.at_time = datetime.time(hour, minute, second)
        elif self.unit == "hours":
            # :MM or MM:SS
            if time_str.startswith(":"):
                m = re.match(r"^:(\d{2})$", time_str)
                if not m:
                    raise ScheduleValueError(
                        f"Invalid time format {time_str!r} for hours unit. "
                        "Expected :MM."
                    )
                minute = int(m.group(1))
                if not 0 <= minute <= 59:
                    raise ScheduleValueError(
                        f"Invalid minute value in {time_str!r}"
                    )
                self.at_time = datetime.time(0, minute)
            else:
                m = re.match(r"^(\d{2}):(\d{2})$", time_str)
                if not m:
                    raise ScheduleValueError(
                        f"Invalid time format {time_str!r} for hours unit. "
                        "Expected :MM or MM:SS."
                    )
                minute, second = int(m.group(1)), int(m.group(2))
                if not (0 <= minute <= 59 and 0 <= second <= 59):
                    raise ScheduleValueError(
                        f"Invalid time values in {time_str!r}"
                    )
                self.at_time = datetime.time(0, minute, second)
        elif self.unit == "minutes":
            # :SS
            m = re.match(r"^:(\d{2})$", time_str)
            if not m:
                raise ScheduleValueError(
                    f"Invalid time format {time_str!r} for minutes unit. "
                    "Expected :SS."
                )
            second = int(m.group(1))
            if not 0 <= second <= 59:
                raise ScheduleValueError(
                    f"Invalid second value in {time_str!r}"
                )
            self.at_time = datetime.time(0, 0, second)
        else:
            raise ScheduleValueError(
                f"at() is not valid for {self.unit!r} unit"
            )

        return self

    def to(self, latest: int) -> Job:
        """Set a random upper-bound for the interval."""
        self.latest = latest
        return self

    def until(
        self,
        until_time: Union[datetime.datetime, datetime.timedelta, datetime.time, str],
    ) -> Job:
        """Set a deadline after which the job will no longer run."""
        if isinstance(until_time, datetime.datetime):
            self.cancel_after = until_time
        elif isinstance(until_time, datetime.timedelta):
            self.cancel_after = datetime.datetime.now() + until_time
        elif isinstance(until_time, datetime.time):
            self.cancel_after = datetime.datetime.combine(
                datetime.date.today(), until_time
            )
            if self.cancel_after < datetime.datetime.now():
                self.cancel_after += datetime.timedelta(days=1)
        elif isinstance(until_time, str):
            # Parse "HH:MM" or "HH:MM:SS" or "YYYY-MM-DD HH:MM:SS"
            if " " in until_time and "-" in until_time:
                self.cancel_after = datetime.datetime.fromisoformat(until_time)
            else:
                parts = until_time.split(":")
                if len(parts) == 2:
                    t = datetime.time(int(parts[0]), int(parts[1]))
                elif len(parts) == 3:
                    t = datetime.time(int(parts[0]), int(parts[1]), int(parts[2]))
                else:
                    raise ScheduleValueError(f"Invalid until time: {until_time!r}")
                self.cancel_after = datetime.datetime.combine(
                    datetime.date.today(), t
                )
                if self.cancel_after < datetime.datetime.now():
                    self.cancel_after += datetime.timedelta(days=1)
        else:
            raise ScheduleValueError(
                f"Invalid until_time type: {type(until_time)}"
            )
        return self

    def do(self, job_func: Callable[..., Any], *args: Any, **kwargs: Any) -> Job:
        """Set the function to execute and schedule the first run."""
        self.job_func = functools.partial(job_func, *args, **kwargs)
        functools.update_wrapper(self.job_func, job_func)
        self._schedule_next_run()
        if self.scheduler is not None:
            self.scheduler.jobs.append(self)
        return self

    def tag(self, *tags: Hashable) -> Job:
        """Tag this job for filtering."""
        self.tags.update(tags)
        return self

    def run(self) -> Any:
        """Run the job now, reschedule, and return the result."""
        if self.job_func is None:
            raise ScheduleValueError("No job function set. Call .do() first.")

        result = self.job_func()
        self.last_run = datetime.datetime.now()
        self._schedule_next_run()

        # Check CancelJob sentinel.
        if isinstance(result, CancelJob) or result is CancelJob:
            if self.scheduler is not None:
                self.scheduler.cancel_job(self)
            return result

        # Check deadline.
        if self.cancel_after is not None and datetime.datetime.now() >= self.cancel_after:
            if self.scheduler is not None:
                self.scheduler.cancel_job(self)
            return result

        return result

    @property
    def should_run(self) -> bool:
        """Return ``True`` if the job should be run now."""
        if self.next_run is None:
            return False
        return datetime.datetime.now() >= self.next_run

    # -----------------------------------------------------------------------
    # Scheduling internals
    # -----------------------------------------------------------------------

    def _schedule_next_run(self) -> None:
        """Calculate the next run time."""
        if self.unit is None:
            raise ScheduleValueError("No time unit set")

        # Determine the actual interval (with jitter if .to() was used).
        interval = self.interval
        if self.latest is not None:
            if self.latest < self.interval:
                raise IntervalError(
                    f"latest ({self.latest}) must be >= interval ({self.interval})"
                )
            interval = random.randint(self.interval, self.latest)

        self.period = _UNIT_TO_DELTA[self.unit](interval)

        now = datetime.datetime.now()
        self.next_run = now + self.period

        if self.at_time is not None:
            if self.unit == "days" and self.start_day is None:
                # Daily job at a specific time.
                self.next_run = now.replace(
                    hour=self.at_time.hour,
                    minute=self.at_time.minute,
                    second=self.at_time.second,
                    microsecond=0,
                )
                # If we've already passed today's time, schedule for tomorrow.
                if self.next_run <= now:
                    self.next_run += self.period
            elif self.unit == "weeks" and self.start_day is not None:
                # Weekday job at a specific time.
                weekday_num = _WEEKDAY_MAP[self.start_day]
                days_ahead = weekday_num - now.weekday()
                if days_ahead < 0:
                    days_ahead += 7
                self.next_run = now.replace(
                    hour=self.at_time.hour,
                    minute=self.at_time.minute,
                    second=self.at_time.second,
                    microsecond=0,
                ) + datetime.timedelta(days=days_ahead)
                if self.next_run <= now:
                    self.next_run += datetime.timedelta(weeks=self.interval)
            elif self.unit == "weeks" and self.start_day is None:
                # Weekly (no weekday) at a specific time.
                self.next_run = now.replace(
                    hour=self.at_time.hour,
                    minute=self.at_time.minute,
                    second=self.at_time.second,
                    microsecond=0,
                )
                if self.next_run <= now:
                    self.next_run += self.period
            elif self.unit == "hours":
                self.next_run = now.replace(
                    minute=self.at_time.minute,
                    second=self.at_time.second,
                    microsecond=0,
                )
                if self.next_run <= now:
                    self.next_run += self.period
            elif self.unit == "minutes":
                self.next_run = now.replace(
                    second=self.at_time.second,
                    microsecond=0,
                )
                if self.next_run <= now:
                    self.next_run += self.period
        elif self.start_day is not None:
            # Weekday job without at_time.
            weekday_num = _WEEKDAY_MAP[self.start_day]
            days_ahead = weekday_num - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            self.next_run = (
                now.replace(hour=0, minute=0, second=0, microsecond=0)
                + datetime.timedelta(days=days_ahead)
            )


_UNIT_TO_DELTA = {
    "seconds": lambda n: datetime.timedelta(seconds=n),
    "minutes": lambda n: datetime.timedelta(minutes=n),
    "hours": lambda n: datetime.timedelta(hours=n),
    "days": lambda n: datetime.timedelta(days=n),
    "weeks": lambda n: datetime.timedelta(weeks=n),
}

_WEEKDAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class Scheduler:
    """Manages and runs a collection of scheduled :class:`Job` instances."""

    def __init__(self) -> None:
        self.jobs: List[Job] = []

    def every(self, interval: int = 1) -> Job:
        """Create a new :class:`Job` attached to this scheduler."""
        job = Job(interval, scheduler=self)
        return job

    def run_pending(self) -> None:
        """Run all jobs that are scheduled to run now."""
        # Sort by next_run so the earliest jobs run first.
        runnable = sorted(
            [j for j in self.jobs if j.should_run]
        )
        for job in runnable:
            self._run_job(job)

    def run_all(self, delay_seconds: int = 0) -> None:
        """Run all jobs immediately, optionally with a delay between each."""
        for job in sorted(self.jobs):
            self._run_job(job)
            if delay_seconds > 0:
                _time.sleep(delay_seconds)

    def get_jobs(self, tag: Optional[Hashable] = None) -> List[Job]:
        """Return jobs, optionally filtered by tag."""
        if tag is None:
            return self.jobs[:]
        return [j for j in self.jobs if tag in j.tags]

    def clear(self, tag: Optional[Hashable] = None) -> None:
        """Cancel all jobs, or only those with the given tag."""
        if tag is None:
            self.jobs[:] = []
        else:
            self.jobs[:] = [j for j in self.jobs if tag not in j.tags]

    def cancel_job(self, job: Job) -> None:
        """Remove a specific job from the scheduler."""
        try:
            self.jobs.remove(job)
        except ValueError:
            pass

    def get_next_run(self, tag: Optional[Hashable] = None) -> Optional[datetime.datetime]:
        """Return the next run time across all (or tagged) jobs."""
        jobs = self.get_jobs(tag)
        if not jobs:
            return None
        return min(jobs).next_run

    @property
    def next_run(self) -> Optional[datetime.datetime]:
        """Return the earliest next-run time across all jobs."""
        return self.get_next_run()

    @property
    def idle_seconds(self) -> Optional[float]:
        """Seconds until the next job should run, or ``None``."""
        nr = self.next_run
        if nr is None:
            return None
        return max(0.0, (nr - datetime.datetime.now()).total_seconds())

    def _run_job(self, job: Job) -> Any:
        return job.run()


# ---------------------------------------------------------------------------
# Module-level API (delegates to default_scheduler)
# ---------------------------------------------------------------------------

default_scheduler: Scheduler = Scheduler()


def every(interval: int = 1) -> Job:
    """Create a new :class:`Job` on the default scheduler."""
    return default_scheduler.every(interval)


def run_pending() -> None:
    """Run all pending jobs on the default scheduler."""
    default_scheduler.run_pending()


def run_all(delay_seconds: int = 0) -> None:
    """Run all jobs on the default scheduler."""
    default_scheduler.run_all(delay_seconds)


def get_jobs(tag: Optional[Hashable] = None) -> List[Job]:
    """Return jobs from the default scheduler."""
    return default_scheduler.get_jobs(tag)


def clear(tag: Optional[Hashable] = None) -> None:
    """Clear jobs from the default scheduler."""
    default_scheduler.clear(tag)


def cancel_job(job: Job) -> None:
    """Cancel a job on the default scheduler."""
    default_scheduler.cancel_job(job)


def next_run() -> Optional[datetime.datetime]:
    """Return the next run time on the default scheduler."""
    return default_scheduler.next_run


def idle_seconds() -> Optional[float]:
    """Return seconds until next run on the default scheduler."""
    return default_scheduler.idle_seconds


def repeat(job: Job, *args: Any, **kwargs: Any) -> Callable[..., Any]:
    """Decorator that schedules a function as a repeating job.

    Usage::

        @repeat(every(10).minutes)
        def task():
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        job.do(func, *args, **kwargs)
        return func
    return decorator
