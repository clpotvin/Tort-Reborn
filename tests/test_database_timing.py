"""
Test suite for DB timing proxies (Helpers/database.py).

Tests:
1. execute() is timed into db.query
2. Non-timed cursor methods delegate unchanged
3. commit() is timed into db.commit
4. Non-timed connection methods delegate unchanged
5. A raising execute() still records and re-raises
"""

import os
import sys

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Helpers import telemetry
from Helpers.database import _TimedConnection, _TimedCursor


@pytest.fixture(autouse=True)
def _reset_context():
    token = telemetry._current.set(None)
    yield
    telemetry._current.reset(token)


class FakeCursor:
    def __init__(self):
        self.executed = []
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return ("row",)

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self):
        self.committed = False
        self.closed = False

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_execute_is_timed_into_db_query():
    telemetry.begin("test", None, None, None)
    cursor = _TimedCursor(FakeCursor())
    cursor.execute("SELECT 1", None)
    assert telemetry._current.get().buckets["db.query"]["n"] == 1


def test_cursor_delegates_untimed_methods():
    inner = FakeCursor()
    cursor = _TimedCursor(inner)
    assert cursor.fetchone() == ("row",)
    cursor.close()
    assert inner.closed is True


def test_commit_is_timed_into_db_commit():
    telemetry.begin("test", None, None, None)
    inner = FakeConnection()
    connection = _TimedConnection(inner)
    connection.commit()
    assert inner.committed is True
    assert telemetry._current.get().buckets["db.commit"]["n"] == 1


def test_connection_delegates_untimed_methods():
    inner = FakeConnection()
    connection = _TimedConnection(inner)
    connection.close()
    assert inner.closed is True


def test_failing_execute_records_and_reraises():
    class Boom:
        def execute(self, *args, **kwargs):
            raise RuntimeError("bad sql")

    telemetry.begin("test", None, None, None)
    cursor = _TimedCursor(Boom())
    with pytest.raises(RuntimeError, match="bad sql"):
        cursor.execute("SELECT 1")
    assert telemetry._current.get().buckets["db.query"]["n"] == 1
