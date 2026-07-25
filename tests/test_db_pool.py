"""
Test suite for the DB connection pool (Helpers/database.py).

Tests:
1. close() returns the connection to the pool after rollback, not conn.close()
2. A broken (closed) connection is discarded with putconn(close=True)
3. Two sequential DB() uses reuse one underlying connection
4. connect() wraps the checkout in the db.connect bucket
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Helpers import database, telemetry


class FakeConn:
    def __init__(self):
        self.closed = 0
        self.rolled_back = False

    def cursor(self):
        return MagicMock()

    def rollback(self):
        self.rolled_back = True


@pytest.fixture(autouse=True)
def _fresh_pool_and_context():
    token = telemetry._current.set(None)
    database._reset_pool_for_tests()
    yield
    database._reset_pool_for_tests()
    telemetry._current.reset(token)


def _fake_pool(conn):
    fake = MagicMock()
    fake.getconn.return_value = conn
    return fake


def test_close_rolls_back_and_returns_to_pool():
    conn = FakeConn()
    fake = _fake_pool(conn)
    with patch.object(database, "_get_pool", return_value=fake):
        db = database.DB()
        db.connect()
        db.close()
    assert conn.rolled_back is True
    fake.putconn.assert_called_once()
    args, kwargs = fake.putconn.call_args
    assert args[0] is conn
    assert not kwargs.get("close", False)


def test_broken_connection_is_discarded():
    conn = FakeConn()
    conn.closed = 1  # psycopg2 marks broken connections with nonzero .closed
    fake = _fake_pool(conn)
    with patch.object(database, "_get_pool", return_value=fake):
        db = database.DB()
        db.connect()
        db.close()
    fake.putconn.assert_called_once_with(conn, close=True)


def test_sequential_uses_share_one_connection():
    conn = FakeConn()
    fake = _fake_pool(conn)
    with patch.object(database, "_get_pool", return_value=fake):
        for _ in range(2):
            db = database.DB()
            db.connect()
            db.close()
    assert fake.getconn.call_count == 2
    assert fake.putconn.call_count == 2  # same pool, checkout/return both times


def test_checkout_is_timed_into_db_connect():
    conn = FakeConn()
    fake = _fake_pool(conn)
    telemetry.begin("test", None, None, None)
    with patch.object(database, "_get_pool", return_value=fake):
        db = database.DB()
        db.connect()
    assert telemetry._current.get().buckets["db.connect"]["n"] == 1
