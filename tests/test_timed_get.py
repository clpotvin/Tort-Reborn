"""
Test suite for outbound HTTP timing (Helpers/functions.timed_get).

Tests:
1. Timing lands in a bucket named for the URL's host
2. The response object is returned unchanged
3. A URL with no parseable host uses the 'unknown' bucket
4. The shared session never stores or sends cookies (stateless across token identities)
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
    with patch("Helpers.functions._session.get", return_value="response") as mock_get:
        result = timed_get("https://api.wynncraft.com/v3/player/x", timeout=10)
    assert result == "response"
    mock_get.assert_called_once_with("https://api.wynncraft.com/v3/player/x", timeout=10)
    assert telemetry._current.get().buckets["http.api.wynncraft.com"]["n"] == 1


def test_timed_get_without_host_uses_unknown():
    telemetry.begin("test", None, None, None)
    with patch("Helpers.functions._session.get", return_value="response"):
        timed_get("not-a-url")
    assert telemetry._current.get().buckets["http.unknown"]["n"] == 1


def test_timed_get_uses_shared_session():
    """All calls must go through the module-level session (keep-alive), never
    bare requests.get — that is the entire point of the session."""
    from Helpers import functions

    assert isinstance(functions._session, __import__("requests").Session)
    with patch("Helpers.functions._session.get", return_value="r") as mock_get, \
         patch("Helpers.functions.requests.get") as mock_bare:
        out = timed_get("https://api.wynncraft.com/v3/x")
    assert out == "r"
    mock_get.assert_called_once()
    mock_bare.assert_not_called()


def test_session_blocks_all_cookies():
    """The session is shared across three token identities; a shared cookie
    jar (e.g. Cloudflare's __cf_bm) would leak state between them and isn't
    thread-safe to write. The policy must refuse to set or send cookies."""
    from Helpers import functions

    policy = functions._session.cookies.get_policy()
    assert policy.set_ok(None, None) is False
    assert policy.return_ok(None, None) is False
