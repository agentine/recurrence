# recurrence

A zero-dependency, modern Python replacement for [schedule](https://github.com/dbader/schedule) — with async support, thread safety, monthly scheduling, timezone awareness via `zoneinfo`, structured error handling, and concurrent job execution.

[![PyPI](https://img.shields.io/pypi/v/recurrence)](https://pypi.org/project/recurrence/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://pypi.org/project/recurrence/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Why recurrence?

`schedule` is the most-downloaded Python in-process job scheduler (9M+ monthly PyPI installs) but has been largely unmaintained since mid-2024. Its most-requested features have never been implemented:

| Feature | schedule | recurrence |
|---|---|---|
| Async / await support | No | Yes |
| Thread safety | No | Yes |
| Monthly scheduling | No | Yes |
| Per-job error handling | No | Yes |
| Concurrent job execution | No | Yes |
| Timezone via stdlib `zoneinfo` | No (pytz only) | Yes |
| Pluggable clock for testing | No | Yes |
| Double-execution prevention | No | Yes |

`recurrence` is a strict superset of the `schedule` API. Existing code migrates with a one-line import change.

---

## Installation

```bash
pip install recurrence
```

Python 3.9+ is required. No runtime dependencies. `zoneinfo` is part of the standard library from Python 3.9 onward.

---

## Quickstart

```python
import recurrence
import time

def greet():
    print("Hello!")

recurrence.every(10).seconds.do(greet)
recurrence.every(2).hours.do(greet)
recurrence.every().monday.at("09:00").do(greet)

while True:
    recurrence.run_pending()
    time.sleep(1)
```

---

## Basic API (schedule-compatible)

### Module-level functions

These functions operate on the built-in `default_scheduler` singleton — the same pattern used by `schedule`.

```python
import recurrence

recurrence.every(10).seconds.do(fn)   # schedule a job
recurrence.run_pending()              # run jobs that are due now
recurrence.run_all()                  # run all jobs immediately
recurrence.clear()                    # remove all jobs
recurrence.cancel_job(job)           # remove one job
recurrence.next_run()                # datetime of the next scheduled job
recurrence.idle_seconds()            # seconds until next job (float or None)
recurrence.get_jobs()                # list all jobs
recurrence.get_jobs(tag="reports")   # filter by tag
recurrence.jobs                      # direct access to the jobs list
```

### Standard run loop

```python
import time
import recurrence

recurrence.every(5).minutes.do(my_task)

while True:
    recurrence.run_pending()
    time.sleep(1)
```

### Scheduling units

```python
recurrence.every().second.do(fn)
recurrence.every(10).seconds.do(fn)
recurrence.every().minute.do(fn)
recurrence.every(5).minutes.do(fn)
recurrence.every().hour.do(fn)
recurrence.every(2).hours.do(fn)
recurrence.every().day.do(fn)
recurrence.every(3).days.do(fn)
recurrence.every().week.do(fn)
recurrence.every(2).weeks.do(fn)
```

Singular forms (`second`, `minute`, `hour`, `day`, `week`) require `interval == 1` and raise `IntervalError` otherwise.

---

## Fluent Job API

### `.at(time_str)` — pin to a specific time

The format depends on the unit:

| Unit | Format | Example |
|---|---|---|
| `day` / weekday | `"HH:MM"` or `"HH:MM:SS"` | `"10:30"`, `"10:30:00"` |
| `hour` | `":MM"` (minutes past the hour) | `":45"` |
| `hour` | `"MM:SS"` (minutes and seconds) | `"30:00"` |
| `minute` | `":SS"` (seconds past the minute) | `":30"` |
| `month` | `"DD HH:MM"` or `"last HH:MM"` | `"15 10:30"`, `"last 18:00"` |

```python
recurrence.every().day.at("10:30").do(fn)
recurrence.every().hour.at(":30").do(fn)       # at HH:30:00 each hour
recurrence.every(2).hours.at("30:00").do(fn)   # at 30 min 0 sec each 2-hour cycle
recurrence.every().minute.at(":15").do(fn)     # at second 15 of each minute
```

### `.to(latest)` — random interval

Pick a random interval between `interval` and `latest` on each reschedule:

```python
recurrence.every(5).to(10).seconds.do(fn)   # run every 5–10 seconds
```

### `.until(deadline)` — auto-cancel after a deadline

```python
import datetime

# Stop running after a specific datetime
recurrence.every().hour.until(datetime.datetime(2026, 12, 31, 23, 59)).do(fn)

# Stop after a duration from now
recurrence.every(10).minutes.until(datetime.timedelta(hours=4)).do(fn)

# Stop at a time today (rolls over to tomorrow if already past)
recurrence.every(5).minutes.until(datetime.time(18, 0)).do(fn)

# Stop at a time string (HH:MM or HH:MM:SS)
recurrence.every(5).minutes.until("18:00").do(fn)

# Stop at an ISO datetime string
recurrence.every().hour.until("2026-12-31 23:59:00").do(fn)
```

### `.tag(*tags)` — group jobs for selective cancellation

```python
recurrence.every(10).seconds.do(fn).tag("worker", "background")
recurrence.every().hour.do(report).tag("reports")

recurrence.clear("reports")          # cancel only report jobs
recurrence.get_jobs("background")    # list background jobs
```

### `.on_error(handler)` — per-job error callback

```python
def handle(job, exc):
    print(f"{job} failed: {exc}")

recurrence.every(10).seconds.do(risky).on_error(handle)
```

### `CancelJob` — self-cancelling jobs

Return `CancelJob` (class or instance) from a job function to remove it after the current run:

```python
import recurrence

counter = {"n": 0}

def run_three_times():
    counter["n"] += 1
    if counter["n"] >= 3:
        return recurrence.CancelJob

recurrence.every(5).seconds.do(run_three_times)
```

---

## Weekday Scheduling

```python
recurrence.every().monday.do(fn)
recurrence.every().tuesday.at("07:00").do(fn)
recurrence.every().wednesday.do(fn)
recurrence.every().thursday.do(fn)
recurrence.every().friday.at("17:00").do(fn)
recurrence.every().saturday.do(fn)
recurrence.every().sunday.do(fn)
```

Weekday properties require `interval == 1` and raise `IntervalError` otherwise.

---

## Timezone Support

Pass a timezone to `Scheduler` or to `.at()` directly. Both string names and `ZoneInfo` objects are accepted.

```python
from zoneinfo import ZoneInfo
from recurrence import Scheduler

# Scheduler-wide timezone
s = Scheduler(timezone="America/New_York")
s.every().day.at("09:00").do(fn)

# Per-job timezone override via .at()
recurrence.every().day.at("09:00", tz="Europe/Berlin").do(fn)

# ZoneInfo object
s = Scheduler(timezone=ZoneInfo("Asia/Tokyo"))
```

Scheduling is DST-aware. Legacy `pytz` objects are also accepted.

---

## Async Support

Pass any `async def` function to `.do()`. `recurrence` auto-detects coroutine functions.

```python
import asyncio
import recurrence

async def fetch_data():
    await asyncio.sleep(0)
    print("fetched")

recurrence.every(30).seconds.do(fetch_data)

async def main():
    while True:
        await recurrence.run_pending_async()
        await asyncio.sleep(1)

asyncio.run(main())
```

`run_pending_async()` is available both at the module level and on `Scheduler` instances:

```python
from recurrence import Scheduler

s = Scheduler()
s.every(10).seconds.do(fetch_data)

async def main():
    while True:
        await s.run_pending_async()
        await asyncio.sleep(1)
```

Mixed sync/async jobs in the same scheduler are supported. `run_pending_async()` dispatches each job appropriately.

---

## Thread Safety

`Scheduler` protects its internal job list with a `threading.RLock`. You can safely add, cancel, and run jobs from different threads.

```python
import threading
import recurrence

def worker():
    recurrence.every(5).seconds.do(lambda: print("from thread"))

t = threading.Thread(target=worker)
t.start()

while True:
    recurrence.run_pending()
    time.sleep(1)
```

**Double-execution prevention:** each job carries a `_running` flag. If `run_pending()` is called concurrently (e.g. from a thread pool) while a slow job is still executing, that job will not be re-entered until it completes.

---

## Monthly Scheduling

`recurrence` adds `.month` / `.months` units not available in `schedule`:

```python
# First of every month at 09:00
recurrence.every().month.at("1 09:00").do(monthly_report)

# 15th of every month at 10:30
recurrence.every().month.at("15 10:30").do(mid_month_task)

# Last day of every month at 18:00
recurrence.every().month.at("last 18:00").do(end_of_month_task)

# Every 3 months on the 1st at 09:00
recurrence.every(3).months.at("1 09:00").do(quarterly_task)

# Once a month (no pinned day — uses calendar arithmetic from now)
recurrence.every().month.do(fn)
```

The `at()` format for months is `"DD HH:MM"` or `"last HH:MM"` where `DD` is `1`–`31` (clamped to the actual month length) or the literal string `last`.

---

## Exception Handling

By default, unhandled job exceptions are logged at `ERROR` level and the scheduler continues. You can override this at the scheduler or job level.

### Scheduler-level handler

```python
import logging
from recurrence import Scheduler

def on_error(job, exc):
    logging.error("Job %r raised %s: %s", job, type(exc).__name__, exc)

s = Scheduler(on_error=on_error)
s.every(10).seconds.do(risky_function)
```

### Per-job handler (fluent, overrides scheduler handler)

```python
def job_error(job, exc):
    print(f"This specific job failed: {exc}")

recurrence.every(5).seconds.do(risky).on_error(job_error)
```

If no handler is set (neither per-job nor scheduler-level), the exception is logged via the `recurrence` logger.

---

## Concurrent Execution

By default jobs run serially within `run_pending()`. Pass `max_workers` to run them concurrently in a `ThreadPoolExecutor`:

```python
from recurrence import Scheduler

s = Scheduler(max_workers=4)
s.every(1).seconds.do(slow_job_a)
s.every(1).seconds.do(slow_job_b)
s.every(1).seconds.do(slow_job_c)

# All three run in parallel on each tick
s.run_pending()

# Clean up the thread pool when done
s.shutdown()
```

---

## Pluggable Clock (Testing)

Inject a custom clock to control time in tests:

```python
import datetime
from recurrence import Scheduler, Clock

class FakeClock:
    def __init__(self, dt: datetime.datetime):
        self._dt = dt

    def now(self, tz=None) -> datetime.datetime:
        return self._dt

clock = FakeClock(datetime.datetime(2026, 1, 15, 10, 0, 0))
s = Scheduler(clock=clock)
s.every(10).seconds.do(lambda: print("ran"))

assert s.next_run == datetime.datetime(2026, 1, 15, 10, 0, 10)
```

`Clock` is a `Protocol` — any object with a `.now(tz=None) -> datetime.datetime` method qualifies.

---

## `repeat` Decorator

Schedule a function declaratively at definition time:

```python
from recurrence import repeat, every

@repeat(every(10).minutes)
def cleanup():
    ...

@repeat(every().day.at("08:00"), "Alice")
def greet(name):
    print(f"Good morning, {name}!")
```

---

## `Scheduler` Class Reference

```python
from recurrence import Scheduler

s = Scheduler(
    timezone="America/New_York",   # str, ZoneInfo, or pytz tzinfo
    clock=my_clock,                # Clock protocol: .now(tz) -> datetime
    on_error=my_handler,           # callable(job: Job, exc: Exception)
    max_workers=4,                 # enable concurrent execution
)

s.every(10).seconds.do(fn)
s.run_pending()
await s.run_pending_async()
s.run_all(delay_seconds=0)
s.clear()
s.clear(tag="reports")
s.cancel_job(job)
s.get_jobs()
s.get_jobs(tag="reports")
s.next_run        # property: earliest next-run datetime or None
s.idle_seconds    # property: float seconds until next run or None
s.shutdown()      # shut down thread pool (call when done if max_workers set)
```

---

## Exceptions

```python
from recurrence import ScheduleError, ScheduleValueError, IntervalError

# ScheduleError           — base class for all recurrence exceptions
# ScheduleValueError      — invalid value passed to a scheduling method
# IntervalError           — invalid interval (< 1, or singular used with n > 1)
```

---

## Migration from schedule

### One-line import swap

```python
# Before
import schedule

# After
import recurrence as schedule
```

All existing `schedule` code continues to work unchanged. `recurrence` exports every name that `schedule` exports (`every`, `run_pending`, `run_all`, `clear`, `cancel_job`, `next_run`, `idle_seconds`, `repeat`, `jobs`, `CancelJob`, `Job`, `Scheduler`, `ScheduleError`, `ScheduleValueError`, `IntervalError`).

### Differences to be aware of

| Behaviour | schedule | recurrence |
|---|---|---|
| `every(0)` / `every(-1)` | Silent / undefined | Raises `IntervalError` immediately |
| Unhandled job exception | Crashes the run loop | Logged, loop continues |
| `next_run` module-level | Property on module | Function: `recurrence.next_run()` |
| `idle_seconds` module-level | Property on module | Function: `recurrence.idle_seconds()` |
| Timezone backend | pytz | `zoneinfo` (stdlib); pytz objects still accepted |

`next_run` and `idle_seconds` are **properties** on `Scheduler` instances but **functions** at module level — this matches the `schedule` module's behaviour for module-level calls.

### Gradual migration example

```python
# Step 1: swap the import — everything works as before
import recurrence as schedule

schedule.every(10).seconds.do(my_job)

while True:
    schedule.run_pending()
    time.sleep(1)
```

```python
# Step 2: adopt recurrence features at your own pace
import recurrence

recurrence.every(10).seconds.do(my_job).on_error(log_error)

async def main():
    while True:
        await recurrence.run_pending_async()
        await asyncio.sleep(1)
```

---

## License

MIT — see [LICENSE](LICENSE).
