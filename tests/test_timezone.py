"""Tests for timezone-aware scheduling, Clock interface, and enhanced at()."""

from __future__ import annotations

import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import pytest

import recurrence
from recurrence.scheduler import Scheduler, Job, Clock, _resolve_tz
from recurrence.exceptions import ScheduleValueError


# ---------------------------------------------------------------------------
# Fake clock for deterministic testing
# ---------------------------------------------------------------------------

class FakeClock:
    """A Clock that returns a controllable time."""

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
# Clock interface tests
# ---------------------------------------------------------------------------

class TestClock:
    def test_fake_clock(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        assert s._now() == t

    def test_fake_clock_advance(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        clock.advance(datetime.timedelta(hours=1))
        assert clock.now() == datetime.datetime(2026, 3, 12, 11, 0, 0)

    def test_scheduler_uses_clock_for_scheduling(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(5).seconds.do(lambda: None)
        expected = t + datetime.timedelta(seconds=5)
        assert job.next_run == expected

    def test_should_run_respects_clock(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(5).seconds.do(lambda: None)
        assert not job.should_run
        clock.advance(datetime.timedelta(seconds=5))
        assert job.should_run

    def test_run_updates_last_run_from_clock(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(5).seconds.do(lambda: None)
        clock.advance(datetime.timedelta(seconds=5))
        job.run()
        assert job.last_run == t + datetime.timedelta(seconds=5)


# ---------------------------------------------------------------------------
# Timezone tests
# ---------------------------------------------------------------------------

class TestTimezone:
    def test_scheduler_with_timezone_string(self) -> None:
        s = Scheduler(timezone="America/New_York")
        assert s.timezone is not None
        assert str(s.timezone) == "America/New_York"

    def test_scheduler_with_zoneinfo(self) -> None:
        tz = ZoneInfo("Europe/London")
        s = Scheduler(timezone=tz)
        assert s.timezone == tz

    def test_scheduler_now_is_timezone_aware(self) -> None:
        s = Scheduler(timezone="UTC")
        now = s._now()
        assert now.tzinfo is not None

    def test_job_inherits_scheduler_tz(self) -> None:
        utc = ZoneInfo("UTC")
        t = datetime.datetime(2026, 3, 12, 10, 0, 0, tzinfo=utc)
        clock = FakeClock(t)
        s = Scheduler(timezone="UTC", clock=clock)
        job = s.every(1).day.at("15:00").do(lambda: None)
        assert job.next_run is not None
        assert job.next_run.tzinfo is not None

    def test_at_with_tz_override(self) -> None:
        utc = ZoneInfo("UTC")
        t = datetime.datetime(2026, 3, 12, 10, 0, 0, tzinfo=utc)
        clock = FakeClock(t)
        s = Scheduler(timezone="UTC", clock=clock)
        job = s.every(1).day.at("15:00", tz="America/New_York").do(lambda: None)
        assert job.at_time_zone is not None
        assert str(job.at_time_zone) == "America/New_York"

    def test_resolve_tz_string(self) -> None:
        tz = _resolve_tz("America/Chicago")
        assert isinstance(tz, datetime.tzinfo)

    def test_resolve_tz_tzinfo(self) -> None:
        tz = ZoneInfo("UTC")
        result = _resolve_tz(tz)
        assert result is tz

    def test_resolve_tz_invalid(self) -> None:
        with pytest.raises(ScheduleValueError):
            _resolve_tz(12345)

    def test_idle_seconds_with_clock(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        s.every(60).seconds.do(lambda: None)
        idle = s.idle_seconds
        assert idle is not None
        assert abs(idle - 60.0) < 1.0


# ---------------------------------------------------------------------------
# at() edge cases
# ---------------------------------------------------------------------------

class TestAtEdgeCases:
    def test_at_seconds_unit_raises(self) -> None:
        s = Scheduler()
        with pytest.raises(ScheduleValueError, match="not meaningful"):
            s.every(1).second.at(":30")

    def test_at_no_unit_raises(self) -> None:
        s = Scheduler()
        job = Job(1, scheduler=s)
        with pytest.raises(ScheduleValueError, match="only valid"):
            job.at("10:00")

    def test_daily_at_schedules_tomorrow_if_past(self) -> None:
        # 10:00 AM, at() for 09:00 → next day 09:00
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(1).day.at("09:00").do(lambda: None)
        assert job.next_run is not None
        assert job.next_run.day == 13  # tomorrow
        assert job.next_run.hour == 9

    def test_daily_at_schedules_today_if_future(self) -> None:
        # 10:00 AM, at() for 15:00 → today 15:00
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(1).day.at("15:00").do(lambda: None)
        assert job.next_run is not None
        assert job.next_run.day == 12  # today
        assert job.next_run.hour == 15

    def test_hourly_at_colon_mm(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 30, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(1).hour.at(":45").do(lambda: None)
        assert job.next_run is not None
        assert job.next_run.minute == 45

    def test_hourly_at_mm_ss(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(1).hour.at("30:15").do(lambda: None)
        assert job.next_run is not None
        assert job.next_run.minute == 30
        assert job.next_run.second == 15

    def test_minute_at_ss(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(1).minute.at(":30").do(lambda: None)
        assert job.next_run is not None
        assert job.next_run.second == 30


# ---------------------------------------------------------------------------
# until() with clock
# ---------------------------------------------------------------------------

class TestUntilWithClock:
    def test_until_timedelta_uses_clock(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(5).seconds
        job.until(datetime.timedelta(hours=1))
        assert job.cancel_after == t + datetime.timedelta(hours=1)

    def test_until_time_uses_clock(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(5).seconds
        job.until(datetime.time(23, 0))
        assert job.cancel_after is not None
        assert job.cancel_after.hour == 23
        assert job.cancel_after.day == 12

    def test_until_time_wraps_to_tomorrow(self) -> None:
        t = datetime.datetime(2026, 3, 12, 23, 30, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(5).seconds
        job.until(datetime.time(1, 0))
        assert job.cancel_after is not None
        assert job.cancel_after.day == 13  # tomorrow

    def test_until_string_uses_clock(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        job = s.every(5).seconds
        job.until("23:00")
        assert job.cancel_after is not None
        assert job.cancel_after.hour == 23

    def test_job_cancelled_after_deadline(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        counter = {"n": 0}

        def task():
            counter["n"] += 1

        job = s.every(5).seconds.do(task)
        job.until(datetime.timedelta(seconds=10))

        # First run at t+5s → within deadline
        clock.advance(datetime.timedelta(seconds=5))
        s.run_pending()
        assert counter["n"] == 1
        assert len(s.jobs) == 1

        # Second run at t+10s → at deadline, job should be cancelled after run
        clock.advance(datetime.timedelta(seconds=5))
        s.run_pending()
        assert counter["n"] == 2
        assert len(s.jobs) == 0  # cancelled


# ---------------------------------------------------------------------------
# Scheduler.get_next_run with tag
# ---------------------------------------------------------------------------

class TestGetNextRunTag:
    def test_get_next_run_filtered(self) -> None:
        t = datetime.datetime(2026, 3, 12, 10, 0, 0)
        clock = FakeClock(t)
        s = Scheduler(clock=clock)
        s.every(10).seconds.tag("fast").do(lambda: None)
        s.every(60).seconds.tag("slow").do(lambda: None)
        nr = s.get_next_run(tag="fast")
        assert nr is not None
        assert nr == t + datetime.timedelta(seconds=10)

    def test_get_next_run_no_match(self) -> None:
        s = Scheduler()
        s.every(10).seconds.do(lambda: None)
        assert s.get_next_run(tag="nonexistent") is None
