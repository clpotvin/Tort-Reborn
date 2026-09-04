"""
Test suite for outbound HTTP timing (Helpers/functions.timed_get).

Tests:
1. Timing lands in a bucket named for the URL's host
2. The response object is returned unchanged
3. A URL with no parseable host uses the 'unknown' bucket
4. Each call opens its own session (no shared/pooled connection)
5. The per-call session never stores or sends cookies (stateless across token identities)
"""

import os
import sys
from unittest.mock import patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Helpers import telemetry
from Helpers.functions import timed_get, _BlockAllCookies, _retry


@pytest.fixture(autouse=True)
def _reset_context():
    token = telemetry._current.set(None)
    yield
    telemetry._current.reset(token)


def test_timed_get_buckets_by_host():
    telemetry.begin("test", None, None, None)
    with patch("requests.Session.get", return_value="response") as mock_get:
        result = timed_get("https://api.wynncraft.com/v3/player/x", timeout=10)
    assert result == "response"
    mock_get.assert_called_once_with("https://api.wynncraft.com/v3/player/x", timeout=10)
    assert telemetry._current.get().buckets["http.api.wynncraft.com"]["n"] == 1


def test_timed_get_without_host_uses_unknown():
    telemetry.begin("test", None, None, None)
    with patch("requests.Session.get", return_value="response"):
        timed_get("not-a-url")
    assert telemetry._current.get().buckets["http.unknown"]["n"] == 1


def test_timed_get_opens_a_fresh_session_per_call():
    from Helpers import functions

    assert not hasattr(functions, "_session")
    with patch("requests.Session.get", return_value="r") as mock_get:
        timed_get("https://api.wynncraft.com/v3/x")
        timed_get("https://api.wynncraft.com/v3/y")
    assert mock_get.call_count == 2


def test_session_blocks_all_cookies():
    policy = _BlockAllCookies()
    assert policy.set_ok(None, None) is False
    assert policy.return_ok(None, None) is False


def test_timed_get_applies_default_timeout():
    """Timeout-less callers get a 15s default instead of hanging forever."""
    with patch("requests.Session.get", return_value="r") as mock_get:
        timed_get("https://api.mojang.com/x")
    assert mock_get.call_args.kwargs["timeout"] == 15


def test_timed_get_explicit_timeout_wins():
    with patch("requests.Session.get", return_value="r") as mock_get:
        timed_get("https://api.wynncraft.com/x", timeout=6)
    assert mock_get.call_args.kwargs["timeout"] == 6


def test_retry_covers_transient_get_failures():
    assert _retry.connect == 2
    assert _retry.read == 1
    assert 502 in _retry.status_forcelist
    assert _retry.allowed_methods == frozenset({"GET"})
