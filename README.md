# recurrence

A zero-dependency, modern Python replacement for [schedule](https://github.com/dbader/schedule) — with async support, thread safety, monthly scheduling, a pluggable Clock protocol, structured error handling, and concurrent job execution.

## Installation

```bash
pip install recurrence
```

## Quickstart

```python
import recurrence

def greet():
    print("Hello!")

# Run every 10 seconds
recurrence.every(10).seconds.do(greet)

# Run every Monday at 9am
recurrence.every().monday.at("09:00").do(greet)

# Run every 2 hours
recurrence.every(2).hours.do(greet)

# Main loop
import time
while True:
    recurrence.run_pending()
    time.sleep(1)
```

## Key Features

### Async Support

Schedule coroutines directly — no boilerplate needed:

```python
import asyncio
import recurrence

async def fetch_data():
    await asyncio.sleep(0)
    print("fetched")

recurrence.every(30).seconds.do(fetch_data)

# In an async context, use run_pending_async:
async def main():
    while True:
        await recurrence.default_scheduler.run_pending_async()
        await asyncio.sleep(1)

asyncio.run(main())
```

### Thread-Safe

`Scheduler` uses an internal `threading.RLock` so jobs can be added or cancelled from any thread without data races.

### Monthly Scheduling

```python
# Run on the 1st of every month at midnight (approximate — uses calendar arithmetic)
recurrence.every().month.at("00:00").do(my_monthly_report)
```

### Clock Protocol

Inject a custom clock for deterministic testing:

```python
import datetime
from recurrence import Scheduler

class FakeClock:
    def __init__(self, dt):
        self._dt = dt
    def now(self, tz=None):
        return self._dt

clock = FakeClock(datetime.datetime(2024, 6, 1, 12, 0, 0))
scheduler = Scheduler(clock=clock)
scheduler.every(10).seconds.do(lambda: print("ran"))
```

### Error Handling

Provide a per-scheduler or per-job error handler instead of crashing the loop:

```python
def handle_error(job, exc):
    print(f"Job {job} failed: {exc}")

scheduler = recurrence.Scheduler(on_error=handle_error)
scheduler.every(5).seconds.do(risky_function)

# Or per-job:
job = recurrence.Job(on_error=handle_error)
scheduler.every(5).seconds.do(risky_function)
```

### Concurrent Execution

Run jobs in a thread pool so slow jobs don't block each other:

```python
scheduler = recurrence.Scheduler(max_workers=4)
scheduler.every(1).seconds.do(slow_job)
scheduler.every(1).seconds.do(another_slow_job)
scheduler.run_pending()  # both run concurrently
```

## Migration from schedule

One-line import change:

```python
# Before
import schedule

# After
import recurrence as schedule
```

Everything else stays the same. `recurrence` is a strict superset of the `schedule` API.

## API Reference

### Module-level functions (default scheduler)

| Function | Description |
|---|---|
| `every(interval=1)` | Create a new job on the default scheduler |
| `run_pending()` | Run all jobs that are due |
| `run_all(delay_seconds=0)` | Run all jobs immediately |
| `get_jobs(tag=None)` | Return all jobs, optionally filtered by tag |
| `clear(tag=None)` | Remove all jobs, or only those with the given tag |
| `cancel_job(job)` | Remove a specific job |
| `next_run()` | Datetime of the next scheduled run |
| `idle_seconds()` | Seconds until the next job runs |
| `repeat(job, *args, **kwargs)` | Decorator to schedule a function |

### Job fluent API

```python
every(10).seconds.do(fn)
every(5).minutes.do(fn)
every(2).hours.at(":30").do(fn)
every().day.at("10:30").do(fn)
every().monday.at("09:00").do(fn)
every().month.at("00:00").do(fn)

# Random interval
every(5).to(10).seconds.do(fn)

# Deadline
every(1).hours.until("18:00").do(fn)

# Tags
every(10).seconds.do(fn).tag("my-tag")

# Cancel from within the job
def my_job():
    return recurrence.CancelJob  # removes itself after running
```

### Scheduler class

```python
s = recurrence.Scheduler(
    timezone="America/New_York",  # str, zoneinfo.ZoneInfo, or pytz tz
    clock=my_clock,               # any object with .now(tz) -> datetime
    on_error=my_handler,          # callable(job, exc)
    max_workers=4,                # enable concurrent execution
)
s.every(10).seconds.do(fn)
s.run_pending()
await s.run_pending_async()
s.shutdown()  # clean up thread pool
```

## License

MIT
