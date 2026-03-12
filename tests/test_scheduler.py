"""Tests for recurrence Scheduler and Job — schedule-compatible behavior."""

from __future__ import annotations

import datetime
import time
from unittest.mock import patch

import pytest

import recurrence
from recurrence import CancelJob, Job, Scheduler
from recurrence.exceptions import IntervalError, ScheduleValueError


# ---------------------------------------------------------------------------
# Scheduler basics
# ---------------------------------------------------------------------------


class TestScheduler:
    def setup_method(self) -> None:
        self.scheduler = Scheduler()

    def test_empty_scheduler(self) -> None:
        assert self.scheduler.jobs == []
        assert self.scheduler.next_run is None
        assert self.scheduler.idle_seconds is None

    def test_every_returns_job(self) -> None:
        job = self.scheduler.every(5)
        assert isinstance(job, Job)
        assert job.interval == 5

    def test_run_pending(self) -> None:
        results: list[str] = []
        self.scheduler.every(1).seconds.do(lambda: results.append("ran"))
        time.sleep(1.1)
        self.scheduler.run_pending()
        assert results == ["ran"]

    def test_run_all(self) -> None:
        results: list[str] = []
        self.scheduler.every(999).seconds.do(lambda: results.append("a"))
        self.scheduler.every(999).seconds.do(lambda: results.append("b"))
        self.scheduler.run_all()
        assert sorted(results) == ["a", "b"]

    def test_get_jobs_no_tag(self) -> None:
        self.scheduler.every(1).seconds.do(lambda: None)
        self.scheduler.every(1).seconds.do(lambda: None)
        assert len(self.scheduler.get_jobs()) == 2

    def test_get_jobs_with_tag(self) -> None:
        self.scheduler.every(1).seconds.do(lambda: None).tag("a")
        self.scheduler.every(1).seconds.do(lambda: None).tag("b")
        assert len(self.scheduler.get_jobs("a")) == 1
        assert len(self.scheduler.get_jobs("b")) == 1

    def test_clear_all(self) -> None:
        self.scheduler.every(1).seconds.do(lambda: None)
        self.scheduler.clear()
        assert self.scheduler.jobs == []

    def test_clear_by_tag(self) -> None:
        self.scheduler.every(1).seconds.do(lambda: None).tag("keep")
        self.scheduler.every(1).seconds.do(lambda: None).tag("remove")
        self.scheduler.clear("remove")
        assert len(self.scheduler.jobs) == 1
        assert "keep" in self.scheduler.jobs[0].tags

    def test_cancel_job(self) -> None:
        job = self.scheduler.every(1).seconds.do(lambda: None)
        self.scheduler.cancel_job(job)
        assert job not in self.scheduler.jobs

    def test_cancel_nonexistent_job(self) -> None:
        job = Job(1)
        self.scheduler.cancel_job(job)  # should not raise

    def test_next_run_property(self) -> None:
        self.scheduler.every(10).seconds.do(lambda: None)
        assert self.scheduler.next_run is not None
        assert self.scheduler.next_run > datetime.datetime.now()

    def test_idle_seconds_positive(self) -> None:
        self.scheduler.every(60).seconds.do(lambda: None)
        idle = self.scheduler.idle_seconds
        assert idle is not None
        assert idle > 0

    def test_get_next_run_with_tag(self) -> None:
        self.scheduler.every(10).seconds.do(lambda: None).tag("x")
        self.scheduler.every(20).seconds.do(lambda: None).tag("y")
        nr = self.scheduler.get_next_run("x")
        assert nr is not None


# ---------------------------------------------------------------------------
# Job fluent API
# ---------------------------------------------------------------------------


class TestJobUnits:
    def setup_method(self) -> None:
        self.scheduler = Scheduler()

    def test_seconds(self) -> None:
        job = self.scheduler.every(5).seconds.do(lambda: None)
        assert job.unit == "seconds"
        assert job.interval == 5

    def test_minutes(self) -> None:
        job = self.scheduler.every(10).minutes.do(lambda: None)
        assert job.unit == "minutes"

    def test_hours(self) -> None:
        job = self.scheduler.every(2).hours.do(lambda: None)
        assert job.unit == "hours"

    def test_days(self) -> None:
        job = self.scheduler.every(3).days.do(lambda: None)
        assert job.unit == "days"

    def test_weeks(self) -> None:
        job = self.scheduler.every(1).weeks.do(lambda: None)
        assert job.unit == "weeks"

    def test_singular_second(self) -> None:
        job = self.scheduler.every(1).second.do(lambda: None)
        assert job.unit == "seconds"

    def test_singular_with_interval_gt_1_raises(self) -> None:
        with pytest.raises(IntervalError):
            self.scheduler.every(2).second


class TestJobWeekdays:
    def setup_method(self) -> None:
        self.scheduler = Scheduler()

    def test_monday(self) -> None:
        job = self.scheduler.every().monday.do(lambda: None)
        assert job.start_day == "monday"
        assert job.unit == "weeks"

    def test_all_weekdays(self) -> None:
        for day in ["monday", "tuesday", "wednesday", "thursday",
                     "friday", "saturday", "sunday"]:
            s = Scheduler()
            job = s.every()
            getattr(job, day)
            assert job.start_day == day

    def test_weekday_with_interval_gt_1_raises(self) -> None:
        with pytest.raises(IntervalError):
            self.scheduler.every(2).monday


class TestJobAt:
    def setup_method(self) -> None:
        self.scheduler = Scheduler()

    def test_daily_at(self) -> None:
        job = self.scheduler.every().day.at("10:30").do(lambda: None)
        assert job.at_time == datetime.time(10, 30)

    def test_daily_at_with_seconds(self) -> None:
        job = self.scheduler.every().day.at("10:30:45").do(lambda: None)
        assert job.at_time == datetime.time(10, 30, 45)

    def test_hourly_at(self) -> None:
        job = self.scheduler.every().hour.at(":30").do(lambda: None)
        assert job.at_time == datetime.time(0, 30)

    def test_hourly_at_mm_ss(self) -> None:
        job = self.scheduler.every().hour.at("45:00").do(lambda: None)
        assert job.at_time == datetime.time(0, 45, 0)

    def test_minute_at(self) -> None:
        job = self.scheduler.every().minute.at(":15").do(lambda: None)
        assert job.at_time == datetime.time(0, 0, 15)

    def test_weekday_at(self) -> None:
        job = self.scheduler.every().monday.at("09:00").do(lambda: None)
        assert job.at_time == datetime.time(9, 0)
        assert job.start_day == "monday"

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ScheduleValueError):
            self.scheduler.every().day.at("invalid")


class TestJobTo:
    def test_random_interval(self) -> None:
        s = Scheduler()
        job = s.every(5).to(10).seconds.do(lambda: None)
        assert job.latest == 10
        # Period should be between 5 and 10 seconds.
        assert datetime.timedelta(seconds=5) <= job.period <= datetime.timedelta(seconds=10)


class TestJobUntil:
    def test_until_datetime(self) -> None:
        s = Scheduler()
        deadline = datetime.datetime.now() + datetime.timedelta(hours=1)
        job = s.every(1).seconds.until(deadline).do(lambda: None)
        assert job.cancel_after == deadline

    def test_until_timedelta(self) -> None:
        s = Scheduler()
        before = datetime.datetime.now()
        job = s.every(1).seconds.until(datetime.timedelta(hours=2)).do(lambda: None)
        assert job.cancel_after is not None
        assert job.cancel_after >= before + datetime.timedelta(hours=2) - datetime.timedelta(seconds=1)

    def test_until_string(self) -> None:
        s = Scheduler()
        job = s.every(1).seconds.until("23:59").do(lambda: None)
        assert job.cancel_after is not None


class TestJobDo:
    def test_do_sets_function(self) -> None:
        s = Scheduler()

        def task():
            return 42

        job = s.every(1).seconds.do(task)
        assert job.job_func is not None
        assert job.job_func() == 42

    def test_do_with_args(self) -> None:
        s = Scheduler()
        results: list[str] = []

        def task(x: str, y: str = "default"):
            results.append(f"{x}-{y}")

        s.every(1).seconds.do(task, "hello", y="world")
        time.sleep(1.1)
        s.run_pending()
        assert results == ["hello-world"]

    def test_do_adds_to_scheduler(self) -> None:
        s = Scheduler()
        s.every(1).seconds.do(lambda: None)
        assert len(s.jobs) == 1


class TestJobRun:
    def test_run_executes(self) -> None:
        s = Scheduler()
        results: list[int] = []
        job = s.every(1).seconds.do(lambda: results.append(1))
        job.run()
        assert results == [1]

    def test_run_updates_last_run(self) -> None:
        s = Scheduler()
        job = s.every(1).seconds.do(lambda: None)
        assert job.last_run is None
        job.run()
        assert job.last_run is not None

    def test_cancel_job_sentinel(self) -> None:
        s = Scheduler()
        job = s.every(1).seconds.do(lambda: CancelJob)
        assert len(s.jobs) == 1
        job.run()
        assert len(s.jobs) == 0


class TestJobRepr:
    def test_repr(self) -> None:
        s = Scheduler()

        def my_task():
            pass

        job = s.every(5).seconds.do(my_task)
        r = repr(job)
        assert "my_task" in r
        assert "5" in r


# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------


class TestModuleLevel:
    def setup_method(self) -> None:
        recurrence.clear()

    def teardown_method(self) -> None:
        recurrence.clear()

    def test_every(self) -> None:
        job = recurrence.every(1).seconds.do(lambda: None)
        assert isinstance(job, Job)
        assert len(recurrence.get_jobs()) == 1

    def test_run_pending(self) -> None:
        results: list[str] = []
        recurrence.every(1).seconds.do(lambda: results.append("ok"))
        time.sleep(1.1)
        recurrence.run_pending()
        assert results == ["ok"]

    def test_clear(self) -> None:
        recurrence.every(1).seconds.do(lambda: None)
        recurrence.clear()
        assert len(recurrence.get_jobs()) == 0

    def test_next_run(self) -> None:
        recurrence.every(60).seconds.do(lambda: None)
        assert recurrence.next_run() is not None

    def test_idle_seconds(self) -> None:
        recurrence.every(60).seconds.do(lambda: None)
        assert recurrence.idle_seconds() is not None
        assert recurrence.idle_seconds() > 0  # type: ignore[operator]


class TestRepeatDecorator:
    def setup_method(self) -> None:
        recurrence.clear()

    def teardown_method(self) -> None:
        recurrence.clear()

    def test_repeat_basic(self) -> None:
        @recurrence.repeat(recurrence.every(1).seconds)
        def task() -> str:
            return "done"

        assert len(recurrence.get_jobs()) == 1
        assert callable(task)

    def test_repeat_with_args(self) -> None:
        results: list[str] = []

        @recurrence.repeat(recurrence.every(1).seconds, "hello")
        def task(msg: str) -> None:
            results.append(msg)

        time.sleep(1.1)
        recurrence.run_pending()
        assert results == ["hello"]


# ---------------------------------------------------------------------------
# Import compatibility
# ---------------------------------------------------------------------------


class TestImportCompat:
    """Verify the ``import recurrence as schedule`` pattern works."""

    def test_import_as_schedule(self) -> None:
        import recurrence as schedule

        s = schedule.Scheduler()
        assert isinstance(s, Scheduler)

    def test_all_exports(self) -> None:
        expected = {
            "CancelJob", "Job", "Scheduler",
            "ScheduleError", "ScheduleValueError", "IntervalError",
            "default_scheduler", "every", "run_pending", "run_all",
            "get_jobs", "clear", "cancel_job", "next_run", "idle_seconds",
            "repeat", "jobs",
        }
        assert expected.issubset(set(dir(recurrence)))
