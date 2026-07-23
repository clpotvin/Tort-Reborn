"""
Test suite for the event-loop lag monitor (Tasks/loop_lag.py).

Tests:
1. Percentile selection on known inputs
2. Percentile on an empty list
3. Summary emission shape and bucket clearing
"""

import asyncio
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Tasks import loop_lag


def test_percentile_picks_expected_values():
    samples = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert loop_lag._percentile(samples, 0.0) == 1.0
    assert loop_lag._percentile(samples, 0.5) == 3.0
    assert loop_lag._percentile(samples, 1.0) == 5.0


def test_percentile_on_empty_list_returns_zero():
    assert loop_lag._percentile([], 0.5) == 0.0


def test_emit_summary_shape_and_reset(monkeypatch, capsys):
    monkeypatch.setenv("LATENCY_TELEMETRY", "1")

    cog = loop_lag.LoopLag.__new__(loop_lag.LoopLag)
    cog._samples = [10.0, 20.0, 500.0]
    cog._window_started = 0.0

    cog._emit_summary(60.0)

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["type"] == "loop_lag_summary"
    assert payload["n"] == 3
    assert payload["max_ms"] == 500.0
    assert payload["window_s"] == 60.0
    assert cog._samples == []
    assert cog._window_started == 60.0


def test_first_tick_is_noop(monkeypatch):
    """With no prior tick recorded, one tick must not compute drift or emit."""
    monkeypatch.setattr(loop_lag.time, "perf_counter", lambda: 100.0)

    mock_emit = MagicMock()
    monkeypatch.setattr(loop_lag.telemetry, "emit", mock_emit)

    cog = loop_lag.LoopLag.__new__(loop_lag.LoopLag)
    cog._last = None
    cog._samples = []
    cog._window_started = 100.0

    asyncio.run(cog.loop_lag())

    assert cog._samples == []
    assert cog._last == 100.0
    mock_emit.assert_not_called()


def test_sub_threshold_drift_accumulates_silently(monkeypatch):
    """Positive drift below the threshold is recorded but not emitted."""
    sub_threshold_drift_ms = loop_lag.LAG_THRESHOLD_MS / 2.0
    clock = [0.0, loop_lag.INTERVAL_S + sub_threshold_drift_ms / 1000.0]
    monkeypatch.setattr(loop_lag.time, "perf_counter", lambda: clock.pop(0))

    mock_emit = MagicMock()
    monkeypatch.setattr(loop_lag.telemetry, "emit", mock_emit)

    cog = loop_lag.LoopLag.__new__(loop_lag.LoopLag)
    cog._last = None
    cog._samples = []
    cog._window_started = 0.0

    async def run_two_ticks():
        await cog.loop_lag()
        await cog.loop_lag()

    asyncio.run(run_two_ticks())

    assert len(cog._samples) == 1
    assert cog._samples[0] == pytest.approx(sub_threshold_drift_ms, abs=1.0)
    assert cog._samples[0] < loop_lag.LAG_THRESHOLD_MS
    assert not any(
        call.args[0].get("type") == "loop_lag" for call in mock_emit.call_args_list
    )


def test_drift_at_or_above_threshold_emits_loop_lag_record(monkeypatch):
    """Drift at/above the threshold emits exactly one loop_lag record."""
    over_threshold_drift_ms = loop_lag.LAG_THRESHOLD_MS + 10.0
    clock = [0.0, loop_lag.INTERVAL_S + over_threshold_drift_ms / 1000.0]
    monkeypatch.setattr(loop_lag.time, "perf_counter", lambda: clock.pop(0))

    mock_emit = MagicMock()
    monkeypatch.setattr(loop_lag.telemetry, "emit", mock_emit)

    cog = loop_lag.LoopLag.__new__(loop_lag.LoopLag)
    cog._last = None
    cog._samples = []
    cog._window_started = 0.0

    async def run_two_ticks():
        await cog.loop_lag()
        await cog.loop_lag()

    asyncio.run(run_two_ticks())

    mock_emit.assert_called_once()
    payload = mock_emit.call_args[0][0]
    assert payload["type"] == "loop_lag"
    assert payload["drift_ms"] >= loop_lag.LAG_THRESHOLD_MS - 1e-6
