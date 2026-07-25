"""
Test suite for the DB connection pool (Helpers/database.py).

Tests:
1. close() returns the connection to the pool after rollback, not conn.close()
2. A broken (closed) connection is discarded with putconn(close=True)
3. Two sequential DB() uses reuse one underlying connection
4. connect() wraps the checkout in the db.connect bucket
5. A checkout whose post-checkout setup fails is discarded, not leaked
6. connect() retries getconn() on PoolError and succeeds once the pool frees up
7. connect() logs a WARN each time it retries after a PoolError (exhaustion signal)
8. connect() gives up and re-raises PoolError after exhausting retries
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from psycopg2 import pool as _pg_pool

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


class FakeConnBrokenCursor(FakeConn):
    def cursor(self):
        raise RuntimeError("cursor setup failed")


def test_checkout_discarded_when_post_checkout_setup_fails():
    conn = FakeConnBrokenCursor()
    fake = _fake_pool(conn)
    with patch.object(database, "_get_pool", return_value=fake):
        db = database.DB()
        with pytest.raises(RuntimeError):
            db.connect()
    fake.putconn.assert_called_once_with(conn, close=True)


def test_connect_retries_pool_error_then_succeeds():
    conn = FakeConn()
    fake = MagicMock()
    fake.getconn.side_effect = [_pg_pool.PoolError("exhausted"), _pg_pool.PoolError("exhausted"), conn]
    with patch.object(database, "_get_pool", return_value=fake), \
         patch.object(database.time, "sleep") as mock_sleep:
        db = database.DB()
        db.connect()
    assert db.connection is not None
    assert fake.getconn.call_count == 3
    mock_sleep.assert_any_call(0.2)
    mock_sleep.assert_any_call(0.4)


def test_connect_logs_warning_when_pool_exhausted_and_retrying():
    conn = FakeConn()
    fake = MagicMock()
    fake.getconn.side_effect = [_pg_pool.PoolError("exhausted"), _pg_pool.PoolError("exhausted"), conn]
    with patch.object(database, "_get_pool", return_value=fake), \
         patch.object(database.time, "sleep"), \
         patch.object(database, "log") as mock_log:
        db = database.DB()
        db.connect()
    assert db.connection is not None
    warn_messages = [
        call.args[1] for call in mock_log.call_args_list
        if len(call.args) >= 2 and "pool exhausted" in str(call.args[1])
    ]
    assert len(warn_messages) == 2  # one WARN per retried checkout, not the final success


def test_connect_gives_up_after_exhausting_pool_error_retries():
    fake = MagicMock()
    fake.getconn.side_effect = _pg_pool.PoolError("exhausted")
    with patch.object(database, "_get_pool", return_value=fake), \
         patch.object(database.time, "sleep"):
        db = database.DB()
        with pytest.raises(_pg_pool.PoolError):
            db.connect()
    assert fake.getconn.call_count == 3
