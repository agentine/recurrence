"""Tests for Phase 3: thread safety, async, monthly, error handling, max_workers."""

from __future__ import annotations

import asyncio
import datetime
import threading
from typing import Optional

import pytest

from recurrence.scheduler import Scheduler, Job, _add_months
from recurrence.exceptions import IntervalError


# ---------------------------------------------------------------------------
# Fake clock (same as test_timezone.py)
# ---------------------------------------------------------------------------

class FakeClock:
    def __init__(self, now: datetime.datetime) -> None:
        self._now = now

    def now(self, tz: Optional[datetime.tzinfo] = None) -> datetime.datetime:
        if tz is not None and self._now.tzinfo is None:
            return self._now.replace(tzinfo=tz)
        if tz is not None and self._now.tzinfo != tz:
            return self._now.astimezone(tz)
        return self._now

    def advance(self, delta: datetime.timedelta) -> None:
        self._now += delta


# ---------------------------------------------------------------------------
# Thread safety tests
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_add_and_read(self) -> None:
        s = Scheduler()
        errors: list[Exception] = []

        def add_jobs():
            try:
                for _ in range(50):
                    s.every(1).seconds.do(lambda: None)
            except Exception as e:
                errors.append(e)

        def read_jobs():
            try:
                for _ in range(50):
                    s.get_jobs()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=add_jobs),
            threading.Thread(target=read_jobs),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent access: {errors}"
        s.clear()

    def test_concurrent_clear(self) -> None:
        s = Scheduler()
        for _ in range(20):
            s.every(1).seconds.do(lambda: None)

        errors: list[Exception] = []

        def clear_jobs():
            try:
                s.clear()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=clear_jobs) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(s.jobs) == 0


# ---------------------------------------------------------------------------
# Monthly scheduling tests
# ---------------------------------------------------------------------------

class TestMonthlyScheduling:
    def test_month_unit(self) -> None:
        t = datetime.datetime(2026, 1, 15, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(1).month.do(lambda: None)
        assert job.unit == "months"
        assert job.next_run is not None
        assert job.next_run.month == 2

    def test_months_unit(self) -> None:
        t = datetime.datetime(2026, 1, 15, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(3).months.do(lambda: None)
        assert job.next_run is not None
        assert job.next_run.month == 4

    def test_month_singular_interval_gt_1_raises(self) -> None:
        s = Scheduler()
        with pytest.raises(IntervalError):
            s.every(2).month

    def test_month_with_at(self) -> None:
        t = datetime.datetime(2026, 1, 15, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(1).month.at("09:00").do(lambda: None)
        assert job.next_run is not None
        assert job.next_run.month == 2
        assert job.next_run.hour == 9

    def test_month_end_clamping(self) -> None:
        # Jan 31 + 1 month → Feb 28 (2026 is not a leap year)
        t = datetime.datetime(2026, 1, 31, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(1).month.do(lambda: None)
        assert job.next_run is not None
        assert job.next_run.month == 2
        assert job.next_run.day == 28

    def test_add_months_helper(self) -> None:
        dt = datetime.datetime(2026, 11, 15)
        result = _add_months(dt, 3)
        assert result.year == 2027
        assert result.month == 2
        assert result.day == 15

    def test_add_months_december(self) -> None:
        dt = datetime.datetime(2026, 12, 15)
        result = _add_months(dt, 1)
        assert result.year == 2027
        assert result.month == 1


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_job_on_error_called(self) -> None:
        errors: list[tuple[Job, Exception]] = []

        def handler(job, exc):
            errors.append((job, exc))

        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = Job(1, scheduler=s, on_error=handler)
        job.seconds.do(lambda: 1 / 0)
        clock.advance(datetime.timedelta(seconds=1))
        job.run()
        assert len(errors) == 1
        assert isinstance(errors[0][1], ZeroDivisionError)

    def test_scheduler_on_error_called(self) -> None:
        errors: list[tuple[Job, Exception]] = []

        def handler(job, exc):
            errors.append((job, exc))

        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock, on_error=handler)
        s.every(1).seconds.do(lambda: 1 / 0)
        clock.advance(datetime.timedelta(seconds=1))
        s.run_pending()
        assert len(errors) == 1

    def test_error_without_handler_logs(self) -> None:
        """Without an error handler, exceptions are logged but don't crash."""
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        s.every(1).seconds.do(lambda: 1 / 0)
        clock.advance(datetime.timedelta(seconds=1))
        # Should not raise.
        s.run_pending()
        # Job should still be in the scheduler (rescheduled).
        assert len(s.jobs) == 1

    def test_job_on_error_takes_priority(self) -> None:
        scheduler_errors: list[Exception] = []
        job_errors: list[Exception] = []

        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(
            clock=clock,
            on_error=lambda j, e: scheduler_errors.append(e),
        )
        job = Job(1, scheduler=s, on_error=lambda j, e: job_errors.append(e))
        job.seconds.do(lambda: 1 / 0)
        s._add_job(job)  # manually add since do() already added
        clock.advance(datetime.timedelta(seconds=1))
        job.run()
        assert len(job_errors) == 1
        assert len(scheduler_errors) == 0


# ---------------------------------------------------------------------------
# Async support tests
# ---------------------------------------------------------------------------

class TestAsyncSupport:
    def test_async_job_detection(self) -> None:
        s = Scheduler()

        async def async_task():
            return 42

        job = s.every(1).seconds.do(async_task)
        assert job._is_async is True

    def test_sync_job_detection(self) -> None:
        s = Scheduler()
        job = s.every(1).seconds.do(lambda: None)
        assert job._is_async is False

    def test_async_job_runs(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        results: list[int] = []

        async def async_task():
            results.append(42)

        s.every(1).seconds.do(async_task)
        clock.advance(datetime.timedelta(seconds=1))
        s.run_pending()
        assert results == [42]

    def test_run_pending_async(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        results: list[int] = []

        async def async_task():
            results.append(1)

        s.every(1).seconds.do(async_task)
        clock.advance(datetime.timedelta(seconds=1))
        asyncio.run(s.run_pending_async())
        assert results == [1]


# ---------------------------------------------------------------------------
# ThreadPoolExecutor tests
# ---------------------------------------------------------------------------

class TestMaxWorkers:
    def test_max_workers_runs_concurrently(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock, max_workers=2)
        results: list[int] = []
        lock = threading.Lock()

        def task(n):
            with lock:
                results.append(n)

        s.every(1).seconds.do(task, 1)
        s.every(1).seconds.do(task, 2)
        clock.advance(datetime.timedelta(seconds=1))
        s.run_pending()
        assert sorted(results) == [1, 2]
        s.shutdown()

    def test_shutdown_idempotent(self) -> None:
        s = Scheduler(max_workers=1)
        s.shutdown()  # no executor yet
        s.shutdown()  # still no crash
