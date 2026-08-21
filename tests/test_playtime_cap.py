"""TAQ-49: windowed playtime can never exceed the window's physical maximum.

The snapshot-delta math (calendar-date baseline vs. live current data) can
span slightly more than N*24 hours, so /activity, /leaderboard, profile
timed stats, and the aspect-eligibility weekly playtime all clamp through
cap_playtime_window. Deliberately simple: cap at N*24 even if the true
window is a few hours wider.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Helpers.functions import cap_playtime_window


def test_day_window_caps_at_24():
    # The ticket's example: "more than 24 hours in a day period".
    assert cap_playtime_window(25.3, 1) == 24


def test_week_window_caps_at_168():
    assert cap_playtime_window(170, 7) == 168


def test_month_window_caps_at_720():
    assert cap_playtime_window(9999, 30) == 720


def test_value_below_cap_is_untouched():
    assert cap_playtime_window(23.5, 1) == 23.5
    assert cap_playtime_window(0, 7) == 0
    assert cap_playtime_window(167.9, 7) == 167.9


def test_exact_cap_is_untouched():
    assert cap_playtime_window(24, 1) == 24
    assert cap_playtime_window(168, 7) == 168


def test_all_time_windows_are_uncapped():
    # days <= 0 means an all-time view; lifetime playtime passes through.
    assert cap_playtime_window(5000, -1) == 5000
    assert cap_playtime_window(5000, 0) == 5000
    assert cap_playtime_window(5000, None) == 5000
