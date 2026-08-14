"""
Test suite for presence sampling in update_member_data.py

Every 3-minute tick records who is online into 15-minute buckets, plus a row
in presence_ticks. The tick log is what lets consumers tell "nobody online"
apart from "bot was down", so these tests pin down:

1. Bucket flooring to 15-minute boundaries
2. Tick row contents (counts + gap since the previous tick)
3. Only online members land in presence_buckets
4. An empty guild still records a tick (the zero must be observed, not assumed)
5. A duplicate tick does not double-increment the buckets
6. A database failure never propagates into the caller's loop
"""

import datetime
import os
import sys
import types
from datetime import timezone, timedelta
from unittest.mock import MagicMock

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Tasks import update_member_data as umd


NOW = datetime.datetime(2025, 6, 1, 12, 7, 31, 500000, tzinfo=timezone.utc)
UUID_A = "11111111-1111-1111-1111-111111111111"
UUID_B = "22222222-2222-2222-2222-222222222222"


class _FakeCursor:
    def __init__(self, fetch_results):
        self.calls = []
        self._fetch = list(fetch_results)

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self._fetch.pop(0) if self._fetch else None


class _FakeDB:
    def __init__(self, fetch_results):
        self.cursor = _FakeCursor(fetch_results)
        self.connection = MagicMock()
        self.closed = False

    def close(self):
        self.closed = True


def _install(monkeypatch, fetch_results, now=NOW):
    """Wire a fake DB and a frozen clock into the module, return the fake DB."""
    db = _FakeDB(fetch_results)
    monkeypatch.setattr(umd, "_db_connect_with_retry", lambda *a, **k: db)
    monkeypatch.setattr(
        umd, "datetime",
        types.SimpleNamespace(datetime=types.SimpleNamespace(now=lambda tz=None: now)),
    )
    return db


def _find(db, needle):
    """The (sql, params) of the single statement containing needle."""
    matches = [c for c in db.cursor.calls if needle in c[0]]
    assert len(matches) == 1, f"expected exactly one {needle!r} statement, got {len(matches)}"
    return matches[0]


def _has(db, needle):
    return any(needle in c[0] for c in db.cursor.calls)


# ---------------------------------------------------------------------------
# 1 – bucket flooring
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("minute,expected", [
    (0, 0), (7, 0), (14, 0),
    (15, 15), (29, 15),
    (30, 30), (44, 30),
    (45, 45), (59, 45),
])
def test_floor_to_presence_bucket(minute, expected):
    dt = datetime.datetime(2025, 6, 1, 12, minute, 31, 500000, tzinfo=timezone.utc)
    floored = umd._floor_to_presence_bucket(dt)
    assert floored.minute == expected
    assert (floored.second, floored.microsecond) == (0, 0)
    assert floored.hour == 12


# ---------------------------------------------------------------------------
# 2 – tick row contents
# ---------------------------------------------------------------------------

def test_tick_records_counts_and_gap(monkeypatch):
    # Stored ticks are always whole seconds, so a real previous tick has none
    # of NOW's sub-second component.
    previous = NOW.replace(microsecond=0) - timedelta(seconds=183)
    db = _install(monkeypatch, [(previous,), (NOW,)])

    umd._write_presence_sample_sync({UUID_A: True, UUID_B: False}, 40, 1)

    _, params = _find(db, "INSERT INTO presence_ticks")
    tick_at, online_count, member_count, gap, attributed = params
    assert tick_at == NOW.replace(microsecond=0)   # sub-second precision is noise
    assert online_count == 1
    assert member_count == 40
    assert gap == 183
    assert attributed == 1


def test_hidden_members_counted_but_not_attributed(monkeypatch):
    """A member who restricts online_status is in the guild's own count but
    reports online=false per-member, so the two figures must diverge rather
    than the guild total quietly shrinking to what we can name."""
    db = _install(monkeypatch, [(None,), (NOW,)])

    # Guild says 4 online; only 2 are visible in the per-member flags.
    umd._write_presence_sample_sync({UUID_A: True, UUID_B: True}, 150, 4)

    _, params = _find(db, "INSERT INTO presence_ticks")
    assert params[1] == 4          # authoritative
    assert params[4] == 2          # attributable
    # Only the nameable members can land in buckets — that is the limitation,
    # not a reason to deflate the guild-wide count.
    _, bucket_params = _find(db, "INSERT INTO presence_buckets")
    assert sorted(bucket_params[1]) == sorted([UUID_A, UUID_B])


def test_missing_guild_count_falls_back_to_attributed(monkeypatch):
    """A malformed guild payload must not record as zero members online."""
    db = _install(monkeypatch, [(None,), (NOW,)])

    umd._write_presence_sample_sync({UUID_A: True, UUID_B: True}, 150, None)

    _, params = _find(db, "INSERT INTO presence_ticks")
    assert params[1] == 2
    assert params[4] == 2


def test_first_tick_ever_has_null_gap(monkeypatch):
    db = _install(monkeypatch, [(None,), (NOW,)])

    umd._write_presence_sample_sync({UUID_A: True}, 1, 1)

    _, params = _find(db, "INSERT INTO presence_ticks")
    assert params[3] is None


# ---------------------------------------------------------------------------
# 3 – bucket contents
# ---------------------------------------------------------------------------

def test_only_online_members_are_bucketed(monkeypatch):
    db = _install(monkeypatch, [(None,), (NOW,)])

    umd._write_presence_sample_sync({UUID_A: True, UUID_B: False}, 2, 1)

    sql, params = _find(db, "INSERT INTO presence_buckets")
    bucket_start, uuids = params
    assert uuids == [UUID_A]
    assert bucket_start == NOW.replace(minute=0, second=0, microsecond=0)
    assert "samples = presence_buckets.samples + 1" in sql
    db.connection.commit.assert_called_once()


# ---------------------------------------------------------------------------
# 4 – nobody online is a recorded observation
# ---------------------------------------------------------------------------

def test_empty_guild_still_records_a_tick(monkeypatch):
    db = _install(monkeypatch, [(None,), (NOW,)])

    umd._write_presence_sample_sync({UUID_A: False, UUID_B: False}, 2, 0)

    _, params = _find(db, "INSERT INTO presence_ticks")
    assert params[1] == 0
    assert not _has(db, "INSERT INTO presence_buckets")
    db.connection.commit.assert_called_once()


# ---------------------------------------------------------------------------
# 5 – duplicate tick
# ---------------------------------------------------------------------------

def test_duplicate_tick_does_not_increment_buckets(monkeypatch):
    # ON CONFLICT DO NOTHING returned no row: this second was already recorded,
    # and its members were already counted.
    db = _install(monkeypatch, [(NOW - timedelta(seconds=180),), None])

    umd._write_presence_sample_sync({UUID_A: True}, 1, 1)

    assert not _has(db, "INSERT INTO presence_buckets")
    db.connection.commit.assert_not_called()
    assert db.closed


# ---------------------------------------------------------------------------
# 6 – failure isolation
# ---------------------------------------------------------------------------

def test_database_failure_does_not_propagate(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("pool exhausted")

    monkeypatch.setattr(umd, "_db_connect_with_retry", boom)
    monkeypatch.setattr(
        umd, "datetime",
        types.SimpleNamespace(datetime=types.SimpleNamespace(now=lambda tz=None: NOW)),
    )

    umd._write_presence_sample_sync({UUID_A: True}, 1, 1)  # must not raise


def test_connection_is_released_on_query_failure(monkeypatch):
    db = _install(monkeypatch, [(None,), (NOW,)])
    db.cursor.execute = MagicMock(side_effect=RuntimeError("connection reset"))

    umd._write_presence_sample_sync({UUID_A: True}, 1, 1)

    assert db.closed
