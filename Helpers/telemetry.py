"""
Helpers/telemetry.py
Phase 0 latency instrumentation. Emits one JSON object per line on stdout.

This module deliberately does NOT route through Helpers/logger.py. That logger
queues messages to a Discord channel; per-command telemetry there would spam the
channel and add Discord API calls to the very code path being measured.

Nothing here may raise into a caller. A telemetry bug must never be able to break
a command.
"""

import contextvars
import datetime
import json
import os
import sys
import time
from contextlib import contextmanager


def queue_ms_from(created, now=None):
    """Milliseconds between an interaction's creation time and `now`.

    `created` is a timezone-aware datetime (from discord.utils.snowflake_time on
    the interaction id). Returns None on missing/bad input rather than raising —
    a telemetry field must never break a command.
    """
    try:
        if created is None:
            return None
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc)
        return round((now - created).total_seconds() * 1000.0, 2)
    except Exception:
        return None

# Holds the accumulator for the in-flight command invocation.
#
# Code MUTATES the Sample rather than rebinding this variable. asyncio.to_thread
# copies the context into the worker thread, so a rebind there would be invisible
# to the caller, whereas a mutation of the shared object is visible. Much of this
# codebase's blocking work is already threaded, so this distinction matters.
_current: contextvars.ContextVar = contextvars.ContextVar("telemetry_sample", default=None)

_DISABLED_VALUES = ("0", "false", "no")


def enabled() -> bool:
    return os.getenv("LATENCY_TELEMETRY", "1").strip().lower() not in _DISABLED_VALUES


class Sample:
    """Timing accumulator for a single command invocation."""

    def __init__(self, command, guild_id=None, user_id=None, queue_ms=None):
        self.command = command
        self.guild_id = guild_id
        self.user_id = user_id
        self.queue_ms = queue_ms
        self.started = time.perf_counter()
        self.buckets = {}
        # Per-bucket nesting depth, so nested spans are not counted twice.
        self.depth = {}

    def add(self, bucket, seconds):
        ms = seconds * 1000.0
        entry = self.buckets.get(bucket)
        if entry is None:
            self.buckets[bucket] = {"n": 1, "ms": round(ms, 2)}
        else:
            entry["n"] += 1
            entry["ms"] = round(entry["ms"] + ms, 2)

    def payload(self, ok):
        return {
            "type": "command",
            "command": self.command,
            "guild_id": self.guild_id,
            "user_id": self.user_id,
            "queue_ms": self.queue_ms,
            "total_ms": round((time.perf_counter() - self.started) * 1000.0, 2),
            "ok": ok,
            "buckets": self.buckets,
        }


def emit(payload: dict) -> None:
    """Write one JSON line to stdout. Never raises."""
    if not enabled():
        return
    try:
        payload.setdefault("ts", round(time.time(), 3))
        sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def record(bucket: str, seconds: float) -> None:
    """Add a duration to the current invocation. No-op outside one. Never raises."""
    try:
        sample = _current.get()
        if sample is not None:
            sample.add(bucket, seconds)
    except Exception:
        pass


@contextmanager
def track(bucket: str):
    """Time a block into `bucket`.

    Depth-guarded: when spans for the same bucket nest, only the outermost one
    records. The render primitives call each other, so without this the render
    total would be inflated by double counting.

    Records even when the body raises, then lets the exception propagate: slow
    failures are as interesting as slow successes.
    """
    try:
        sample = _current.get()
    except Exception:
        sample = None

    if sample is None:
        yield
        return

    try:
        depth = sample.depth.get(bucket, 0)
        sample.depth[bucket] = depth + 1
    except Exception:
        yield
        return

    # Only the outermost span for a bucket records, so skip the clock reads
    # entirely when nested — this timer sits on the instrumented hot paths
    # (render primitives call each other) and shouldn't add its own overhead.
    start = time.perf_counter() if depth == 0 else None
    try:
        yield
    finally:
        try:
            sample.depth[bucket] = depth
            if depth == 0:
                sample.add(bucket, time.perf_counter() - start)
        except Exception:
            pass


def begin(command, guild_id=None, user_id=None, queue_ms=None):
    """Start an invocation. Never raises."""
    try:
        sample = Sample(command, guild_id, user_id, queue_ms)
        _current.set(sample)
        return sample
    except Exception:
        return None


def finish(ok: bool = True) -> None:
    """Emit the current invocation's record and clear it. Never raises."""
    try:
        sample = _current.get()
        if sample is None:
            return
        _current.set(None)
        emit(sample.payload(ok))
    except Exception:
        pass
