"""
Test suite for Phase 0 latency telemetry (Helpers/telemetry.py).

Tests:
1. Accumulation: repeated track() on one bucket sums duration and counts calls
2. Depth guarding: nested track() on the same bucket records the outer span only
3. Context isolation: concurrent invocations do not contaminate each other
4. Thread propagation: track() inside asyncio.to_thread reaches the caller's sample
5. Exceptions: a raising body still records, and the exception propagates
6. No-op: track() outside an invocation does nothing and does not raise
7. Kill switch: emit() writes nothing when disabled
"""

import asyncio
import os
import sys
import time

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Helpers import telemetry


@pytest.fixture(autouse=True)
def _reset_context():
    token = telemetry._current.set(None)
    yield
    telemetry._current.reset(token)


def test_track_accumulates_count_and_duration():
    telemetry.begin("test", None, None, None)
    for _ in range(2):
        with telemetry.track("db.query"):
            time.sleep(0.01)
    bucket = telemetry._current.get().buckets["db.query"]
    assert bucket["n"] == 2
    assert bucket["ms"] >= 18.0


def test_nested_track_records_outer_span_only():
    telemetry.begin("test", None, None, None)
    with telemetry.track("render"):
        time.sleep(0.01)
        with telemetry.track("render"):
            time.sleep(0.01)
    bucket = telemetry._current.get().buckets["render"]
    assert bucket["n"] == 1
    assert bucket["ms"] >= 18.0


def test_concurrent_invocations_do_not_share_buckets():
    async def invocation(name, bucket):
        telemetry.begin(name, None, None, None)
        with telemetry.track(bucket):
            await asyncio.sleep(0.01)
        return telemetry._current.get()

    async def main():
        return await asyncio.gather(
            invocation("a", "db.query"),
            invocation("b", "s3.get"),
        )

    a, b = asyncio.run(main())
    assert set(a.buckets) == {"db.query"}
    assert set(b.buckets) == {"s3.get"}


def test_track_propagates_into_to_thread():
    def blocking():
        with telemetry.track("db.connect"):
            time.sleep(0.01)

    async def main():
        telemetry.begin("test", None, None, None)
        await asyncio.to_thread(blocking)
        return telemetry._current.get()

    sample = asyncio.run(main())
    assert sample.buckets["db.connect"]["n"] == 1


def test_track_records_and_reraises_on_exception():
    telemetry.begin("test", None, None, None)
    with pytest.raises(ValueError, match="boom"):
        with telemetry.track("http.example.com"):
            raise ValueError("boom")
    assert telemetry._current.get().buckets["http.example.com"]["n"] == 1


def test_track_outside_invocation_is_noop():
    with telemetry.track("db.query"):
        pass  # must not raise


def test_emit_respects_kill_switch(monkeypatch, capsys):
    monkeypatch.setenv("LATENCY_TELEMETRY", "0")
    telemetry.emit({"type": "command"})
    assert capsys.readouterr().out == ""


def test_finish_emits_one_json_line(monkeypatch, capsys):
    monkeypatch.setenv("LATENCY_TELEMETRY", "1")
    telemetry.begin("profile", 1, 2, 12.5)
    with telemetry.track("db.query"):
        pass
    telemetry.finish(ok=True)

    import json
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["type"] == "command"
    assert payload["command"] == "profile"
    assert payload["queue_ms"] == 12.5
    assert payload["ok"] is True
    assert payload["buckets"]["db.query"]["n"] == 1


def test_sys_exc_info_is_visible_inside_async_finally():
    """py-cord runs after_invoke inside a `finally` while an exception propagates.

    `ok` is derived from sys.exc_info() there, so pin that semantic down.
    """
    seen = {}

    async def hook():
        await asyncio.sleep(0)
        seen["exc"] = sys.exc_info()[0]

    async def body():
        try:
            raise ValueError("boom")
        finally:
            await hook()

    async def main():
        with pytest.raises(ValueError):
            await body()

    asyncio.run(main())
    assert seen["exc"] is ValueError


def test_finish_marks_failure(monkeypatch, capsys):
    monkeypatch.setenv("LATENCY_TELEMETRY", "1")
    telemetry.begin("profile", None, None, None)
    telemetry.finish(ok=False)

    import json
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is False
