# recurrence — Drop-in Replacement for schedule

## Overview

**Target:** [schedule](https://github.com/dbader/schedule) — the most popular Python in-process job scheduler
**Package:** `recurrence` on PyPI
**License:** MIT
**Python:** 3.10+
**Dependencies:** Zero required (optional: zoneinfo backport for 3.8)

## Why Replace schedule

- Last commit: May 2024 (~2 years ago)
- 12,247 stars, 9M monthly PyPI downloads
- 177 open issues with no triage
- No async/await support (most requested feature)
- No thread safety (commonly causes bugs in production)
- No monthly scheduling (frequently requested)
- No built-in exception handling (crashes the run loop)
- No concurrent job execution
- Depends on pytz for timezone support (deprecated in favor of zoneinfo)
- Single-threaded only by design
- Original author handed off maintenance, new maintainer also inactive

## Architecture

recurrence is a single-module Python library with a clean layered design:

```
Module-Level API (every, run_pending, clear, etc.)
    ↓ delegates to
Scheduler (job registry, execution loop)
    ↓ manages
Job (fluent builder, scheduling logic, execution)
    ↓ uses
TimeEngine (pluggable clock, timezone handling)
```

The entire library is a single file (~1000 lines) with zero required dependencies.

## Public API Surface (100% schedule compatible)

### Module-Level Functions

```python
default_scheduler: Scheduler  # singleton
jobs: List[Job]               # reference to default_scheduler.jobs

def every(interval: int = 1) -> Job
def run_pending() -> None
def run_all(delay_seconds: int = 0) -> None
def get_jobs(tag: Optional[Hashable] = None) -> List[Job]
def clear(tag: Optional[Hashable] = None) -> None
def cancel_job(job: Job) -> None
def next_run(tag: Optional[Hashable] = None) -> Optional[datetime.datetime]
def idle_seconds() -> Optional[float]
def repeat(job: Job, *args, **kwargs) -> Callable  # decorator
```

### Scheduler Class

```python
class Scheduler:
    jobs: List[Job]

    def every(self, interval: int = 1) -> Job
    def run_pending(self) -> None
    def run_all(self, delay_seconds: int = 0) -> None
    def get_jobs(self, tag: Optional[Hashable] = None) -> List[Job]
    def clear(self, tag: Optional[Hashable] = None) -> None
    def cancel_job(self, job: Job) -> None
    def get_next_run(self, tag: Optional[Hashable] = None) -> Optional[datetime.datetime]

    @property
    def next_run(self) -> Optional[datetime.datetime]
    @property
    def idle_seconds(self) -> Optional[float]
```

### Job Class — Fluent API

```python
class Job:
    interval: int
    latest: Optional[int]
    job_func: Optional[functools.partial]
    unit: Optional[str]
    at_time: Optional[datetime.time]
    at_time_zone: Optional[tzinfo]
    last_run: Optional[datetime.datetime]
    next_run: Optional[datetime.datetime]
    start_day: Optional[str]
    cancel_after: Optional[datetime.datetime]
    tags: Set[Hashable]

    # Time unit properties (return self)
    # Singular (interval must be 1):
    second, minute, hour, day, week

    # Plural:
    seconds, minutes, hours, days, weeks

    # Weekday (interval must be 1, sets start_day):
    monday, tuesday, wednesday, thursday, friday, saturday, sunday

    # Fluent methods
    def at(self, time_str: str, tz: Optional[str] = None) -> Job
    def to(self, latest: int) -> Job
    def until(self, until_time: Union[datetime, timedelta, time, str]) -> Job
    def do(self, job_func: Callable, *args, **kwargs) -> Job
    def tag(self, *tags: Hashable) -> Job
    def run(self) -> Any

    @property
    def should_run(self) -> bool
```

### at() Time Format Rules

| Unit | Format | Example |
|------|--------|---------|
| day/weekday | `HH:MM` or `HH:MM:SS` | `"10:30"`, `"10:30:00"` |
| hour | `:MM` or `MM:SS` | `":30"`, `"45:00"` |
| minute | `:SS` | `":15"` |

### Exceptions

```python
class ScheduleError(Exception): ...
class ScheduleValueError(ScheduleError): ...
class IntervalError(ScheduleValueError): ...
```

### CancelJob Sentinel

```python
class CancelJob: ...
# Returning CancelJob or CancelJob() from a job function cancels the job
```

### repeat Decorator

```python
@repeat(every(10).minutes)
def task():
    ...

@repeat(every().day.at("10:30"), "arg1", key="val")
def task_with_args(arg, key):
    ...
```

## Key Improvements Over schedule

### 1. Async Support (New)
```python
# New: async job functions
async def fetch_data():
    async with aiohttp.ClientSession() as session:
        ...

every(10).minutes.do(fetch_data)  # auto-detected as async

# New: async run loop
await run_pending_async()
```

### 2. Thread Safety (New)
- `Scheduler.jobs` protected by `threading.RLock`
- Safe to call `run_pending()` from one thread and `every().do()` from another
- `run_pending()` acquires lock, snapshots jobs, releases lock, then executes

### 3. Monthly Scheduling (New)
```python
every().month.at("15 10:30")     # 15th of every month at 10:30
every().month.at("last 18:00")   # last day of month at 18:00
every(3).months.at("1 09:00")    # every 3 months on the 1st at 09:00
```

### 4. Exception Handling (New)
```python
# New: per-job exception handler
def on_error(job, exc):
    logging.error(f"Job {job} failed: {exc}")

every(10).seconds.do(task).on_error(on_error)

# New: scheduler-level default handler
scheduler = Scheduler(on_error=on_error)
```

### 5. Timezone Support via zoneinfo (stdlib)
```python
# Uses zoneinfo instead of pytz
every().day.at("10:30", tz="America/New_York")  # same API, stdlib backend
```

### 6. Concurrent Execution (New)
```python
# New: run jobs in a thread pool
scheduler = Scheduler(max_workers=4)
# Jobs execute concurrently up to max_workers
```

### 7. Clock Interface for Testing (New)
```python
# New: injectable clock for deterministic testing
from recurrence import Scheduler, Clock

class FakeClock(Clock):
    def now(self) -> datetime: ...
    def sleep(self, seconds: float): ...

scheduler = Scheduler(clock=FakeClock())
```

## Implementation Phases

### Phase 1: Core Scheduler Engine
- Scheduler class with job registry
- Job class with full fluent API (all unit properties, weekday properties)
- `at()`, `to()`, `until()`, `do()`, `tag()` methods
- `run_pending()`, `run_all()`, `clear()`, `cancel_job()`, `get_jobs()`
- `next_run`, `idle_seconds` properties
- `CancelJob` sentinel
- All 3 exception classes
- `_schedule_next_run()` logic including random intervals and weekday offsets
- Module-level functions delegating to `default_scheduler`
- `repeat` decorator
- Full compatibility with schedule's behavior

### Phase 2: Time & Timezone Engine
- `at()` time format parsing for all units (day/hour/minute)
- DST-aware scheduling using `zoneinfo` (stdlib)
- `until()` deadline support with all accepted formats
- Clock interface for testability
- Backward-compatible `pytz` acceptance in `tz` parameter

### Phase 3: Extensions
- Thread safety via `threading.RLock`
- Async job support (`async def` auto-detection, `run_pending_async()`)
- Monthly scheduling (`.month` / `.months` unit)
- Per-job and scheduler-level exception handling (`on_error`)
- Concurrent execution via `concurrent.futures.ThreadPoolExecutor`
- `max_workers` option on Scheduler

### Phase 4: Polish & Ship
- schedule test suite ported + new tests for extensions
- Performance benchmarks
- Migration guide (import recurrence as schedule)
- PyPI package, CI/CD, documentation
- Compatibility shim for seamless drop-in replacement
