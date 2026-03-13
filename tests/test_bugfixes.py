"""Tests for bug fixes in task #245."""

from __future__ import annotations

import datetime
import threading
import time
from unittest.mock import MagicMock

import pytest

from recurrence import Job, Scheduler
from recurrence.exceptions import IntervalError, ScheduleValueError
from recurrence.scheduler import Clock


# ---------------------------------------------------------------------------
# Bug 1: Concurrent run_pending double-execution
# ---------------------------------------------------------------------------


class TestConcurrentRunPending:
    def test_no_double_execution(self) -> None:
        """Two threads calling run_pending concurrently must not run the same job twice."""
        counter = {"value": 0}
        lock = threading.Lock()

        def slow_job() -> None:
            with lock:
                counter["value"] += 1
            time.sleep(0.1)

        scheduler = Scheduler()
        scheduler.every(1).seconds.do(slow_job)
        # Force the job to be runnable
        scheduler.jobs[0].next_run = datetime.datetime.now() - datetime.timedelta(seconds=1)

        t1 = threading.Thread(target=scheduler.run_pending)
        t2 = threading.Thread(target=scheduler.run_pending)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert counter["value"] == 1, f"Job ran {counter['value']} times, expected 1"


# ---------------------------------------------------------------------------
# Bug 2: Interval validation
# ---------------------------------------------------------------------------


class TestIntervalValidation:
    def test_zero_interval_raises(self) -> None:
        scheduler = Scheduler()
        with pytest.raises(IntervalError, match="must be >= 1"):
            scheduler.every(0).seconds.do(lambda: None)

    def test_negative_interval_raises(self) -> None:
        scheduler = Scheduler()
        with pytest.raises(IntervalError, match="must be >= 1"):
            scheduler.every(-1).seconds.do(lambda: None)

    def test_interval_one_ok(self) -> None:
        scheduler = Scheduler()
        job = scheduler.every(1).seconds.do(lambda: None)
        assert job.interval == 1

    def test_interval_large_ok(self) -> None:
        scheduler = Scheduler()
        job = scheduler.every(100).seconds.do(lambda: None)
        assert job.interval == 100


# ---------------------------------------------------------------------------
# Bug 3: until() ValueError from fromisoformat
# ---------------------------------------------------------------------------


class TestUntilValueError:
    def test_invalid_iso_raises_schedule_error(self) -> None:
        scheduler = Scheduler()
        job = scheduler.every(1).seconds
        with pytest.raises(ScheduleValueError, match="Invalid ISO format"):
            job.until("2026-99-99 25:00:00")

    def test_valid_iso_works(self) -> None:
        scheduler = Scheduler()
        job = scheduler.every(1).seconds
        job.until("2099-12-31 23:59:59")
        assert job.cancel_after is not None


# ---------------------------------------------------------------------------
# Bug 4: Monthly day-of-month syntax
# ---------------------------------------------------------------------------


class _FixedClock:
    """Clock that returns a fixed datetime."""

    def __init__(self, dt: datetime.datetime) -> None:
        self._dt = dt

    def now(self, tz=None):  # type: ignore[override]
        return self._dt


class TestMonthlyDayOfMonth:
    def test_at_15th_1030(self) -> None:
        """at('15 10:30') schedules on the 15th at 10:30."""
        fixed = datetime.datetime(2026, 3, 1, 8, 0, 0)
        scheduler = Scheduler(clock=_FixedClock(fixed))
        job = scheduler.every(1).month.at("15 10:30").do(lambda: None)
        assert job.next_run is not None
        assert job.next_run.day == 15
        assert job.next_run.hour == 10
        assert job.next_run.minute == 30

    def test_at_last_1800(self) -> None:
        """at('last 18:00') schedules on the last day of the next month."""
        fixed = datetime.datetime(2026, 2, 1, 8, 0, 0)
        scheduler = Scheduler(clock=_FixedClock(fixed))
        job = scheduler.every(1).month.at("last 18:00").do(lambda: None)
        assert job.next_run is not None
        # One month from Feb 1 = March; last day of March = 31
        assert job.next_run.month == 3
        assert job.next_run.day == 31
        assert job.next_run.hour == 18

    def test_at_31_clamps_to_month_end(self) -> None:
        """at('31 12:00') on a 30-day month clamps to 30th."""
        fixed = datetime.datetime(2026, 3, 15, 8, 0, 0)
        scheduler = Scheduler(clock=_FixedClock(fixed))
        job = scheduler.every(1).month.at("31 12:00").do(lambda: None)
        assert job.next_run is not None
        # April 2026 has 30 days, so 31 clamps to 30
        assert job.next_run.day == 30
        assert job.next_run.month == 4

    def test_at_invalid_day_raises(self) -> None:
        scheduler = Scheduler()
        with pytest.raises(ScheduleValueError, match="Invalid day-of-month"):
            scheduler.every(1).month.at("0 10:00")

    def test_at_invalid_day_32_raises(self) -> None:
        scheduler = Scheduler()
        with pytest.raises(ScheduleValueError, match="Invalid day-of-month"):
            scheduler.every(1).month.at("32 10:00")

    def test_regular_monthly_at_still_works(self) -> None:
        """Regular at('10:30') without day still works for months."""
        fixed = datetime.datetime(2026, 3, 1, 8, 0, 0)
        scheduler = Scheduler(clock=_FixedClock(fixed))
        job = scheduler.every(1).month.at("10:30").do(lambda: None)
        assert job.next_run is not None
        assert job.at_day is None
        assert job.at_time is not None


# ---------------------------------------------------------------------------
# Bug 5: run_pending_async exported at module level
# ---------------------------------------------------------------------------


class TestRunPendingAsyncExport:
    def test_exported(self) -> None:
        import recurrence
        assert hasattr(recurrence, "run_pending_async")
        assert callable(recurrence.run_pending_async)


# ---------------------------------------------------------------------------
# Bug 6: on_error as fluent method
# ---------------------------------------------------------------------------


class TestOnErrorFluent:
    def test_chained_on_error(self) -> None:
        """on_error() should be chainable as a fluent method."""
        scheduler = Scheduler()
        errors: list = []
        handler = lambda job, exc: errors.append(exc)

        def bad_job() -> None:
            raise RuntimeError("boom")

        job = scheduler.every(1).seconds.do(bad_job).on_error(handler)
        assert isinstance(job, Job)

        # Force job to be runnable and run it
        job.next_run = datetime.datetime.now() - datetime.timedelta(seconds=1)
        scheduler.run_pending()

        assert len(errors) == 1
        assert str(errors[0]) == "boom"


# ---------------------------------------------------------------------------
# Bug 7: _ensure_executor under lock
# ---------------------------------------------------------------------------


class TestEnsureExecutorThreadSafe:
    def test_concurrent_ensure_executor(self) -> None:
        """Two threads calling _ensure_executor should not create two executors."""
        scheduler = Scheduler(max_workers=2)
        barrier = threading.Barrier(2)

        def call_ensure() -> None:
            barrier.wait()
            scheduler._ensure_executor()

        t1 = threading.Thread(target=call_ensure)
        t2 = threading.Thread(target=call_ensure)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Should have exactly one executor
        assert scheduler._executor is not None
        scheduler.shutdown()


# ---------------------------------------------------------------------------
# Bug 8: Clock protocol exported
# ---------------------------------------------------------------------------


class TestClockExport:
    def test_clock_exported(self) -> None:
        import recurrence
        assert hasattr(recurrence, "Clock")
