"""Tests for recurrence._compat — schedule compatibility shim."""

from __future__ import annotations

import recurrence


# ---------------------------------------------------------------------------
# 1. import recurrence as schedule works
# ---------------------------------------------------------------------------

class TestImportAsSchedule:
    """Verify the 'import recurrence as schedule' pattern works end-to-end."""

    def test_module_has_every(self) -> None:
        import recurrence as schedule
        assert callable(schedule.every)

    def test_module_has_run_pending(self) -> None:
        import recurrence as schedule
        assert callable(schedule.run_pending)

    def test_module_has_run_all(self) -> None:
        import recurrence as schedule
        assert callable(schedule.run_all)

    def test_module_has_get_jobs(self) -> None:
        import recurrence as schedule
        assert callable(schedule.get_jobs)

    def test_module_has_clear(self) -> None:
        import recurrence as schedule
        assert callable(schedule.clear)

    def test_module_has_cancel_job(self) -> None:
        import recurrence as schedule
        assert callable(schedule.cancel_job)

    def test_module_has_next_run(self) -> None:
        import recurrence as schedule
        assert callable(schedule.next_run)

    def test_module_has_idle_seconds(self) -> None:
        import recurrence as schedule
        assert callable(schedule.idle_seconds)

    def test_module_has_repeat(self) -> None:
        import recurrence as schedule
        assert callable(schedule.repeat)

    def test_module_has_jobs_list(self) -> None:
        import recurrence as schedule
        # 'jobs' is the list on the default scheduler
        assert isinstance(schedule.jobs, list)

    def test_module_has_cancel_job_class(self) -> None:
        import recurrence as schedule
        assert schedule.CancelJob is not None

    def test_module_has_scheduler_class(self) -> None:
        import recurrence as schedule
        assert schedule.Scheduler is not None

    def test_module_has_job_class(self) -> None:
        import recurrence as schedule
        assert schedule.Job is not None


# ---------------------------------------------------------------------------
# 2. from recurrence._compat import Scheduler, Job works
# ---------------------------------------------------------------------------

class TestCompatImports:
    def test_import_scheduler(self) -> None:
        from recurrence._compat import Scheduler
        assert Scheduler is not None

    def test_import_job(self) -> None:
        from recurrence._compat import Job
        assert Job is not None

    def test_import_every(self) -> None:
        from recurrence._compat import every
        assert callable(every)

    def test_import_run_pending(self) -> None:
        from recurrence._compat import run_pending
        assert callable(run_pending)

    def test_import_run_all(self) -> None:
        from recurrence._compat import run_all
        assert callable(run_all)

    def test_import_get_jobs(self) -> None:
        from recurrence._compat import get_jobs
        assert callable(get_jobs)

    def test_import_clear(self) -> None:
        from recurrence._compat import clear
        assert callable(clear)

    def test_import_cancel_job(self) -> None:
        from recurrence._compat import cancel_job
        assert callable(cancel_job)

    def test_import_next_run(self) -> None:
        from recurrence._compat import next_run
        assert callable(next_run)

    def test_import_idle_seconds(self) -> None:
        from recurrence._compat import idle_seconds
        assert callable(idle_seconds)

    def test_import_repeat(self) -> None:
        from recurrence._compat import repeat
        assert callable(repeat)

    def test_import_cancel_job_sentinel(self) -> None:
        from recurrence._compat import CancelJob
        assert CancelJob is not None

    def test_import_exceptions(self) -> None:
        from recurrence._compat import ScheduleError, ScheduleValueError, IntervalError
        assert issubclass(ScheduleValueError, ScheduleError)
        assert issubclass(IntervalError, ScheduleValueError)

    def test_compat_scheduler_is_same_class(self) -> None:
        from recurrence._compat import Scheduler
        from recurrence import Scheduler as RecurrenceScheduler
        assert Scheduler is RecurrenceScheduler

    def test_compat_job_is_same_class(self) -> None:
        from recurrence._compat import Job
        from recurrence import Job as RecurrenceJob
        assert Job is RecurrenceJob


# ---------------------------------------------------------------------------
# 3. Basic scheduling through the compat shim
# ---------------------------------------------------------------------------

class TestCompatScheduling:
    """Schedule and run jobs via the compat API (isolated Scheduler instance)."""

    def setup_method(self) -> None:
        from recurrence._compat import Scheduler
        self.scheduler = Scheduler()

    def teardown_method(self) -> None:
        self.scheduler.clear()

    def test_schedule_and_run_all(self) -> None:
        from recurrence._compat import Scheduler
        results: list[int] = []
        s = Scheduler()
        s.every(999).seconds.do(lambda: results.append(1))
        s.run_all()
        assert results == [1]

    def test_schedule_multiple_jobs(self) -> None:
        results: list[str] = []
        self.scheduler.every(999).seconds.do(lambda: results.append("a"))
        self.scheduler.every(999).seconds.do(lambda: results.append("b"))
        self.scheduler.run_all()
        assert sorted(results) == ["a", "b"]

    def test_cancel_job_via_compat(self) -> None:
        from recurrence._compat import Scheduler, Job
        s = Scheduler()
        job = s.every(999).seconds.do(lambda: None)
        assert isinstance(job, Job)
        assert len(s.jobs) == 1
        s.cancel_job(job)
        assert len(s.jobs) == 0

    def test_clear_via_compat(self) -> None:
        from recurrence._compat import Scheduler
        s = Scheduler()
        s.every(999).seconds.do(lambda: None)
        s.every(999).seconds.do(lambda: None)
        assert len(s.jobs) == 2
        s.clear()
        assert len(s.jobs) == 0

    def test_tag_filtering_via_compat(self) -> None:
        from recurrence._compat import Scheduler
        s = Scheduler()
        s.every(999).seconds.do(lambda: None).tag("alpha")
        s.every(999).seconds.do(lambda: None).tag("beta")
        alpha_jobs = s.get_jobs("alpha")
        assert len(alpha_jobs) == 1

    def test_cancel_job_sentinel_stops_job(self) -> None:
        from recurrence._compat import Scheduler, CancelJob
        s = Scheduler()
        call_count = [0]

        def job_fn():
            call_count[0] += 1
            return CancelJob

        s.every(999).seconds.do(job_fn)
        s.run_all()
        # job cancels itself, so scheduler should have removed it
        assert len(s.jobs) == 0

    def test_next_run_and_idle_seconds(self) -> None:
        from recurrence._compat import Scheduler
        s = Scheduler()
        assert s.next_run is None
        assert s.idle_seconds is None
        s.every(100).seconds.do(lambda: None)
        assert s.next_run is not None
        assert s.idle_seconds is not None
        assert s.idle_seconds > 0

    def test_get_jobs_returns_all(self) -> None:
        from recurrence._compat import Scheduler
        s = Scheduler()
        s.every(999).seconds.do(lambda: None)
        s.every(888).seconds.do(lambda: None)
        assert len(s.get_jobs()) == 2


# ---------------------------------------------------------------------------
# 4. Module-level convenience functions (default_scheduler delegates)
# ---------------------------------------------------------------------------

class TestModuleLevelFunctions:
    """Module-level functions in recurrence mirror the schedule library API."""

    def setup_method(self) -> None:
        # Clear the default scheduler before each test.
        recurrence.clear()

    def teardown_method(self) -> None:
        recurrence.clear()

    def test_every_adds_to_default_scheduler(self) -> None:
        recurrence.every(999).seconds.do(lambda: None)
        assert len(recurrence.get_jobs()) == 1

    def test_clear_removes_all_jobs(self) -> None:
        recurrence.every(999).seconds.do(lambda: None)
        recurrence.every(999).seconds.do(lambda: None)
        recurrence.clear()
        assert recurrence.get_jobs() == []

    def test_run_all_executes_jobs(self) -> None:
        results: list[int] = []
        recurrence.every(999).seconds.do(lambda: results.append(1))
        recurrence.run_all()
        assert results == [1]

    def test_cancel_job_removes_specific_job(self) -> None:
        job = recurrence.every(999).seconds.do(lambda: None)
        assert len(recurrence.get_jobs()) == 1
        recurrence.cancel_job(job)
        assert len(recurrence.get_jobs()) == 0

    def test_next_run_returns_none_when_empty(self) -> None:
        assert recurrence.next_run() is None

    def test_idle_seconds_returns_none_when_empty(self) -> None:
        assert recurrence.idle_seconds() is None

    def test_next_run_returns_datetime_when_jobs_exist(self) -> None:
        import datetime
        recurrence.every(60).seconds.do(lambda: None)
        nr = recurrence.next_run()
        assert isinstance(nr, datetime.datetime)

    def test_idle_seconds_returns_positive_float(self) -> None:
        recurrence.every(60).seconds.do(lambda: None)
        secs = recurrence.idle_seconds()
        assert secs is not None
        assert secs > 0

    def test_get_jobs_with_tag(self) -> None:
        recurrence.every(999).seconds.do(lambda: None).tag("mytag")
        recurrence.every(999).seconds.do(lambda: None).tag("other")
        tagged = recurrence.get_jobs("mytag")
        assert len(tagged) == 1

    def test_repeat_decorator(self) -> None:
        results: list[int] = []

        @recurrence.repeat(recurrence.every(999).seconds)
        def my_task():
            results.append(42)

        assert len(recurrence.get_jobs()) == 1
        recurrence.run_all()
        assert results == [42]

    def test_jobs_list_attribute(self) -> None:
        # recurrence.jobs is a reference to the default_scheduler jobs list
        recurrence.every(999).seconds.do(lambda: None)
        # Note: recurrence.jobs is captured at import time; use get_jobs() for
        # the live list. The attribute exists and is a list.
        assert isinstance(recurrence.jobs, list)
