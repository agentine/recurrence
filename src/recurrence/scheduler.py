"""Core scheduler and job classes — 100% schedule-compatible API."""

from __future__ import annotations

import asyncio
import calendar
import datetime
import functools
import inspect
import logging
import random
import re
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Hashable, List, Optional, Protocol, Set, Union

from recurrence import CancelJob
from recurrence.exceptions import IntervalError, ScheduleValueError

_logger = logging.getLogger("recurrence")


# ---------------------------------------------------------------------------
# Clock protocol
# ---------------------------------------------------------------------------

class Clock(Protocol):
    """Pluggable clock for deterministic testing."""

    def now(self, tz: Optional[datetime.tzinfo] = None) -> datetime.datetime:
        ...  # pragma: no cover


class _DefaultClock:
    """Uses ``datetime.datetime.now()``."""

    def now(self, tz: Optional[datetime.tzinfo] = None) -> datetime.datetime:
        return datetime.datetime.now(tz)


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

class Job:
    """A periodically-scheduled job, built via a fluent API."""

    def __init__(
        self,
        interval: int = 1,
        scheduler: Optional[Scheduler] = None,
        on_error: Optional[Callable[[Job, Exception], None]] = None,
    ) -> None:
        self.interval: int = interval
        self.latest: Optional[int] = None
        self.job_func: Optional[functools.partial[Any]] = None
        self.unit: Optional[str] = None
        self.at_time: Optional[datetime.time] = None
        self.at_time_zone: Optional[datetime.tzinfo] = None
        self.last_run: Optional[datetime.datetime] = None
        self.next_run: Optional[datetime.datetime] = None
        self.period: Optional[datetime.timedelta] = None
        self.start_day: Optional[str] = None
        self.cancel_after: Optional[datetime.datetime] = None
        self.tags: Set[Hashable] = set()
        self.scheduler: Optional[Scheduler] = scheduler
        self.on_error: Optional[Callable[[Job, Exception], None]] = on_error
        self._is_async: bool = False

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
    # Clock / timezone helpers
    # -----------------------------------------------------------------------

    def _now(self) -> datetime.datetime:
        """Return the current time, respecting scheduler timezone and clock."""
        tz = self._effective_tz()
        if self.scheduler is not None and self.scheduler.clock is not None:
            return self.scheduler.clock.now(tz)
        return datetime.datetime.now(tz)

    def _effective_tz(self) -> Optional[datetime.tzinfo]:
        """Return the timezone to use: job-level at_time_zone > scheduler tz."""
        if self.at_time_zone is not None:
            return self.at_time_zone
        if self.scheduler is not None:
            return self.scheduler.timezone
        return None

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

    @property
    def month(self) -> Job:
        if self.interval != 1:
            raise IntervalError("Use .months instead of .month when interval > 1")
        return self.months

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

    @property
    def months(self) -> Job:
        self.unit = "months"
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
        - day/weekday/month: ``"HH:MM"`` or ``"HH:MM:SS"``
        - hour: ``":MM"`` or ``"MM:SS"``
        - minute: ``":SS"``
        """
        if self.unit not in ("hours", "days", "weeks", "minutes", "seconds", "months"):
            raise ScheduleValueError(
                "at() is only valid for minute/hour/day/week/month units"
            )

        if tz is not None:
            self.at_time_zone = _resolve_tz(tz)

        if self.unit in ("days", "weeks", "months"):
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
        elif self.unit == "seconds":
            raise ScheduleValueError(
                "at() is not meaningful for the seconds unit"
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
        now = self._now()
        if isinstance(until_time, datetime.datetime):
            self.cancel_after = until_time
        elif isinstance(until_time, datetime.timedelta):
            self.cancel_after = now + until_time
        elif isinstance(until_time, datetime.time):
            self.cancel_after = datetime.datetime.combine(
                now.date(), until_time, tzinfo=now.tzinfo
            )
            if self.cancel_after < now:
                self.cancel_after += datetime.timedelta(days=1)
        elif isinstance(until_time, str):
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
                    now.date(), t, tzinfo=now.tzinfo
                )
                if self.cancel_after < now:
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
        self._is_async = inspect.iscoroutinefunction(job_func)
        self._schedule_next_run()
        if self.scheduler is not None:
            self.scheduler._add_job(self)
        return self

    def tag(self, *tags: Hashable) -> Job:
        """Tag this job for filtering."""
        self.tags.update(tags)
        return self

    def run(self) -> Any:
        """Run the job now, reschedule, and return the result."""
        if self.job_func is None:
            raise ScheduleValueError("No job function set. Call .do() first.")

        try:
            if self._is_async:
                result = _run_async(self.job_func)
            else:
                result = self.job_func()
        except Exception as exc:
            handler = self.on_error
            if handler is None and self.scheduler is not None:
                handler = self.scheduler.on_error
            if handler is not None:
                handler(self, exc)
            else:
                _logger.exception("Job %r raised an exception", self)
            self.last_run = self._now()
            self._schedule_next_run()
            return None

        self.last_run = self._now()
        self._schedule_next_run()

        if isinstance(result, CancelJob) or result is CancelJob:
            if self.scheduler is not None:
                self.scheduler.cancel_job(self)
            return result

        if self.cancel_after is not None and self._now() >= self.cancel_after:
            if self.scheduler is not None:
                self.scheduler.cancel_job(self)
            return result

        return result

    @property
    def should_run(self) -> bool:
        """Return ``True`` if the job should be run now."""
        if self.next_run is None:
            return False
        return self._now() >= self.next_run

    # -----------------------------------------------------------------------
    # Scheduling internals
    # -----------------------------------------------------------------------

    def _schedule_next_run(self) -> None:
        """Calculate the next run time."""
        if self.unit is None:
            raise ScheduleValueError("No time unit set")

        interval = self.interval
        if self.latest is not None:
            if self.latest < self.interval:
                raise IntervalError(
                    f"latest ({self.latest}) must be >= interval ({self.interval})"
                )
            interval = random.randint(self.interval, self.latest)

        now = self._now()

        # Monthly scheduling uses calendar arithmetic.
        if self.unit == "months":
            self.period = datetime.timedelta(days=30)  # approximate
            self.next_run = _add_months(now, interval)
            if self.at_time is not None:
                self.next_run = self.next_run.replace(
                    hour=self.at_time.hour,
                    minute=self.at_time.minute,
                    second=self.at_time.second,
                    microsecond=0,
                )
                if self.next_run <= now:
                    self.next_run = _add_months(now, interval + 1)
                    self.next_run = self.next_run.replace(
                        hour=self.at_time.hour,
                        minute=self.at_time.minute,
                        second=self.at_time.second,
                        microsecond=0,
                    )
            return

        self.period = _UNIT_TO_DELTA[self.unit](interval)
        self.next_run = now + self.period

        if self.at_time is not None:
            if self.unit == "days" and self.start_day is None:
                self.next_run = now.replace(
                    hour=self.at_time.hour,
                    minute=self.at_time.minute,
                    second=self.at_time.second,
                    microsecond=0,
                )
                if self.next_run <= now:
                    self.next_run += self.period
            elif self.unit == "weeks" and self.start_day is not None:
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
            weekday_num = _WEEKDAY_MAP[self.start_day]
            days_ahead = weekday_num - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            self.next_run = (
                now.replace(hour=0, minute=0, second=0, microsecond=0)
                + datetime.timedelta(days=days_ahead)
            )


def _add_months(dt: datetime.datetime, months: int) -> datetime.datetime:
    """Add months to a datetime, clamping day to month-end if needed."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, max_day)
    return dt.replace(year=year, month=month, day=day)


def _run_async(func: functools.partial[Any]) -> Any:
    """Run an async job function, creating an event loop if needed."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, func())
            return future.result()
    return asyncio.run(func())


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
# Timezone helpers
# ---------------------------------------------------------------------------

def _resolve_tz(tz: Any) -> datetime.tzinfo:
    """Convert a timezone string or pytz/zoneinfo object to a tzinfo."""
    if isinstance(tz, str):
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]
        return ZoneInfo(tz)
    if isinstance(tz, datetime.tzinfo):
        return tz
    raise ScheduleValueError(f"Invalid timezone: {tz!r}")


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class Scheduler:
    """Manages and runs a collection of scheduled :class:`Job` instances."""

    def __init__(
        self,
        timezone: Optional[Any] = None,
        clock: Optional[Clock] = None,
        on_error: Optional[Callable[[Job, Exception], None]] = None,
        max_workers: Optional[int] = None,
    ) -> None:
        self.jobs: List[Job] = []
        self.timezone: Optional[datetime.tzinfo] = None
        self.clock: Optional[Clock] = clock
        self.on_error: Optional[Callable[[Job, Exception], None]] = on_error
        self._max_workers: Optional[int] = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None
        self._lock = threading.RLock()
        if timezone is not None:
            self.timezone = _resolve_tz(timezone)

    def _add_job(self, job: Job) -> None:
        """Thread-safe job list append."""
        with self._lock:
            self.jobs.append(job)

    def every(self, interval: int = 1) -> Job:
        """Create a new :class:`Job` attached to this scheduler."""
        job = Job(interval, scheduler=self)
        return job

    def run_pending(self) -> None:
        """Run all jobs that are scheduled to run now."""
        with self._lock:
            runnable = sorted(
                [j for j in self.jobs if j.should_run]
            )
        if self._max_workers is not None:
            self._ensure_executor()
            futures = []
            for job in runnable:
                futures.append(self._executor.submit(self._run_job, job))  # type: ignore[union-attr]
            for f in futures:
                f.result()  # wait for all
        else:
            for job in runnable:
                self._run_job(job)

    async def run_pending_async(self) -> None:
        """Awaitable version of run_pending for async contexts."""
        with self._lock:
            runnable = sorted(
                [j for j in self.jobs if j.should_run]
            )
        for job in runnable:
            if job._is_async and job.job_func is not None:
                try:
                    result = await job.job_func()
                except Exception as exc:
                    handler = job.on_error or self.on_error
                    if handler is not None:
                        handler(job, exc)
                    else:
                        _logger.exception("Job %r raised an exception", job)
                    job.last_run = job._now()
                    job._schedule_next_run()
                    continue
                job.last_run = job._now()
                job._schedule_next_run()
                if isinstance(result, CancelJob) or result is CancelJob:
                    self.cancel_job(job)
                elif job.cancel_after is not None and job._now() >= job.cancel_after:
                    self.cancel_job(job)
            else:
                self._run_job(job)

    def run_all(self, delay_seconds: int = 0) -> None:
        """Run all jobs immediately, optionally with a delay between each."""
        with self._lock:
            jobs = sorted(self.jobs[:])
        for job in jobs:
            self._run_job(job)
            if delay_seconds > 0:
                _time.sleep(delay_seconds)

    def get_jobs(self, tag: Optional[Hashable] = None) -> List[Job]:
        """Return jobs, optionally filtered by tag."""
        with self._lock:
            if tag is None:
                return self.jobs[:]
            return [j for j in self.jobs if tag in j.tags]

    def clear(self, tag: Optional[Hashable] = None) -> None:
        """Cancel all jobs, or only those with the given tag."""
        with self._lock:
            if tag is None:
                self.jobs[:] = []
            else:
                self.jobs[:] = [j for j in self.jobs if tag not in j.tags]

    def cancel_job(self, job: Job) -> None:
        """Remove a specific job from the scheduler."""
        with self._lock:
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
        now = self._now()
        return max(0.0, (nr - now).total_seconds())

    def _now(self) -> datetime.datetime:
        """Return current time respecting timezone and clock."""
        if self.clock is not None:
            return self.clock.now(self.timezone)
        return datetime.datetime.now(self.timezone)

    def _run_job(self, job: Job) -> Any:
        return job.run()

    def _ensure_executor(self) -> None:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self._max_workers)

    def shutdown(self) -> None:
        """Shut down the thread pool executor if one was created."""
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None


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
