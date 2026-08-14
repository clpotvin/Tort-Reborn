"""Test suite for Helpers/playtime_daily.py

Shared by the nightly refresh in update_member_data and the CLI backfill, so
the two cannot drift on the rules.

build_rows turns consecutive player_activity snapshots into per-day rows. The
cases that matter are the ones the real history actually contains:

1. A clean one-day delta
2. A member's first snapshot (no baseline)
3. A multi-day span (missed snapshot, or a member who left and rejoined)
4. A negative delta (uuid reuse / API correction)
5. War and raid counters spread across a span without inventing or losing events
6. The 24-hour-per-day ceiling
"""
import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Helpers.playtime_daily import build_rows, MAX_HOURS_PER_DAY

U = "11111111-1111-1111-1111-111111111111"
D1 = datetime.date(2025, 6, 1)


def rec(day, playtime, wars=0, raids=0, prev_date=None,
        prev_playtime=None, prev_wars=None, prev_raids=None):
    return (U, day, playtime, wars, raids, prev_date, prev_playtime, prev_wars, prev_raids)


def test_clean_one_day_delta():
    rows = list(build_rows([rec(D1 + datetime.timedelta(days=1), 105.5,
                                prev_date=D1, prev_playtime=100.0)]))
    assert len(rows) == 1
    uuid, day, hours, wars, raids, span, source = rows[0]
    assert (uuid, day) == (U, D1 + datetime.timedelta(days=1))
    assert hours == pytest.approx(5.5)
    assert (span, source) == (1, "exact")


def test_first_snapshot_produces_no_row():
    """Playtime before a member's first snapshot accrued outside the window,
    so there is no day to attribute it to."""
    assert list(build_rows([rec(D1, 100.0)])) == []


def test_multi_day_span_is_spread_and_flagged():
    rows = list(build_rows([rec(D1 + datetime.timedelta(days=3), 112.0,
                                prev_date=D1, prev_playtime=100.0)]))
    assert [r[1] for r in rows] == [D1 + datetime.timedelta(days=i) for i in (1, 2, 3)]
    assert all(r[2] == pytest.approx(4.0) for r in rows)
    assert all(r[5] == 3 and r[6] == "interpolated" for r in rows)
    assert sum(r[2] for r in rows) == pytest.approx(12.0)


def test_negative_delta_is_clamped_to_zero():
    rows = list(build_rows([rec(D1 + datetime.timedelta(days=1), 10.0, wars=5, raids=2,
                                prev_date=D1, prev_playtime=2299.0,
                                prev_wars=900, prev_raids=400)]))
    assert len(rows) == 1
    assert rows[0][2] == 0.0
    assert (rows[0][3], rows[0][4]) == (0, 0)
    assert rows[0][6] == "clamped"


def test_counters_are_distributed_without_loss():
    """7 wars over a 3-day span must still total 7 — no invented or dropped
    events, remainder on the later days."""
    rows = list(build_rows([rec(D1 + datetime.timedelta(days=3), 106.0, wars=7, raids=4,
                                prev_date=D1, prev_playtime=100.0,
                                prev_wars=0, prev_raids=0)]))
    assert sum(r[3] for r in rows) == 7
    assert sum(r[4] for r in rows) == 4
    assert [r[3] for r in rows] == [2, 2, 3]


def test_counter_regression_floors_without_clamping_playtime():
    """A war-count correction alongside healthy playtime keeps the playtime."""
    rows = list(build_rows([rec(D1 + datetime.timedelta(days=1), 106.0, wars=3,
                                prev_date=D1, prev_playtime=100.0, prev_wars=9)]))
    assert rows[0][2] == pytest.approx(6.0)
    assert rows[0][3] == 0
    assert rows[0][6] == "exact"


def test_hours_are_capped_at_a_full_day_and_labelled():
    """Real data contains 32.2h and 27.5h single-day jumps. Clipping them is
    right; labelling them 'exact' afterwards would not be."""
    rows = list(build_rows([rec(D1 + datetime.timedelta(days=1), 200.0,
                                prev_date=D1, prev_playtime=100.0)]))
    assert rows[0][2] == MAX_HOURS_PER_DAY
    assert rows[0][6] == "capped"


def test_a_long_span_is_not_capped_just_for_a_large_total():
    """158 hours over 51 days is 3.1h/day — unremarkable, and must stay
    'interpolated' rather than being mislabelled as an impossible value."""
    rows = list(build_rows([rec(D1 + datetime.timedelta(days=51), 258.34,
                                prev_date=D1, prev_playtime=100.0)]))
    assert {r[6] for r in rows} == {"interpolated"}


def test_long_gap_stays_within_the_daily_ceiling():
    """The real history has a 51-day span carrying 158 hours; spreading it
    must not produce an impossible day."""
    rows = list(build_rows([rec(D1 + datetime.timedelta(days=51), 258.34,
                                prev_date=D1, prev_playtime=100.0)]))
    assert len(rows) == 51
    assert all(0 <= r[2] <= MAX_HOURS_PER_DAY for r in rows)
    assert sum(r[2] for r in rows) == pytest.approx(158.34, abs=0.05)
    assert rows[0][6] == "interpolated"


def test_rows_are_uniquely_keyed():
    """(uuid, day) is the primary key, so a span must not emit a day twice."""
    records = [
        rec(D1 + datetime.timedelta(days=2), 110.0, prev_date=D1, prev_playtime=100.0),
        rec(D1 + datetime.timedelta(days=3), 115.0,
            prev_date=D1 + datetime.timedelta(days=2), prev_playtime=110.0),
    ]
    rows = list(build_rows(records))
    keys = [(r[0], r[1]) for r in rows]
    assert len(keys) == len(set(keys))
