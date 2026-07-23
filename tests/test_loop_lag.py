"""
Test suite for the event-loop lag monitor (Tasks/loop_lag.py).

Tests:
1. Percentile selection on known inputs
2. Percentile on an empty list
3. Summary emission shape and bucket clearing
"""

import json
import os
import sys

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
