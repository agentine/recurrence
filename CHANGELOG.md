# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-13

Initial release of **recurrence** — a zero-dependency, modern Python replacement for [schedule](https://github.com/dbader/schedule) with async support, thread safety, monthly scheduling, and timezone awareness.

### Added

- **`Scheduler`** — drop-in `schedule`-compatible API: `every(n).seconds/minutes/hours/days/weeks.do(job_func)`, `run_pending()`, `run_all()`, `clear()`, `jobs`, `next_run`, `idle_seconds`.
- **Fluent `Job` API** — `.at(time_str)`, `.until(deadline)`, `.to(n)` (random interval), `.tag(*tags)`, `.do(func, *args, **kwargs)`, `.cancel()`.
- **Interval validation** — `every(0)` and `every(-1)` raise `IntervalError` immediately; previously silently produced infinite loops.
- **Monthly scheduling** — `every().month.at("DD HH:MM")` for once-a-month jobs; not available in the original `schedule`.
- **Thread safety** — all scheduler state protected by `threading.Lock`; safe to call `run_pending()` from multiple threads.
- **Async support** — `async_do(async_func)` and `AsyncScheduler` with `run_pending_async()` for use in `asyncio` event loops.
- **Per-job double-execution prevention** — `_running` flag prevents a slow job from being re-entered by a concurrent `run_pending()` call.
- **`on_error` handler** — fluent `.on_error(handler)` per-job error callback; scheduler continues on job failure.
- **Timezone-aware scheduling** — `every().day.at("09:00", tz="America/New_York")` with pluggable `Clock` interface for testability.
- **`CancelJob` sentinel** — job can return `CancelJob` to remove itself from the schedule (same as `schedule`).
- **Compat shim** — `recurrence.every`, `recurrence.run_pending`, `recurrence.jobs` module-level aliases mirror the `schedule` module API for drop-in replacement.
- **161 tests** covering scheduler core, job fluent API, async, thread safety, timezone, monthly scheduling, compat shim, and bug fixes.

### Fixed

- Concurrent double-execution: per-job `_running` flag prevents re-entry when job is still running.
- `every(0)` / `every(-1)`: raises `IntervalError` instead of silently scheduling an unreachable job.
- `until()`: wraps `fromisoformat` `ValueError` in `ScheduleValueError` with a descriptive message.
- Monthly `at()` syntax: `"DD HH:MM"` format implemented (was previously unimplemented).
- `on_error` fluent method: now chainable (returns `self`).
