"""
Test suite for outbound HTTP timing (Helpers/functions.timed_get).

Tests:
1. Timing lands in a bucket named for the URL's host
2. The response object is returned unchanged
3. A URL with no parseable host uses the 'unknown' bucket
"""

import os
import sys
from unittest.mock import patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Helpers import telemetry
from Helpers.functions import timed_get


@pytest.fixture(autouse=True)
def _reset_context():
    token = telemetry._current.set(None)
    yield
    telemetry._current.reset(token)


def test_timed_get_buckets_by_host():
    telemetry.begin("test", None, None, None)
    with patch("Helpers.functions.requests.get", return_value="response") as mock_get:
        result = timed_get("https://api.wynncraft.com/v3/player/x", timeout=10)
    assert result == "response"
    mock_get.assert_called_once_with("https://api.wynncraft.com/v3/player/x", timeout=10)
    assert telemetry._current.get().buckets["http.api.wynncraft.com"]["n"] == 1


def test_timed_get_without_host_uses_unknown():
    telemetry.begin("test", None, None, None)
    with patch("Helpers.functions.requests.get", return_value="response"):
        timed_get("not-a-url")
    assert telemetry._current.get().buckets["http.unknown"]["n"] == 1
