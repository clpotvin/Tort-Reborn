"""Tests for the territory tracker's write-on-change persistence.

The snapshot write is the bot's dominant egress cost, so the loop must only
write when the fetched data differs from what the DB already holds — while
still rewriting when the row is missing (self-heal after external deletion).
"""

from unittest.mock import MagicMock

import pytest

from Tasks import territory_tracker as tt
from Tasks.territory_tracker import TerritoryTracker


def _terr(guild_name, prefix, acquired="2026-01-01T00:00:00Z"):
    return {
        "guild": {"uuid": "u", "name": guild_name, "prefix": prefix},
        "acquired": acquired,
        "location": {"start": [0, 0], "end": [1, 1]},
    }


def _snapshot():
    return {
        "Alpha Plains": _terr("Guild A", "AAA"),
        "Beta Woods": _terr("Guild B", "BBB"),
    }


def _make_cog():
    cog = TerritoryTracker.__new__(TerritoryTracker)
    client = MagicMock()
    client.is_ready.return_value = True
    # Home tracker channel exists (loop returns early without it);
    # global/military channels absent so no embeds are attempted.
    client.get_channel.side_effect = (
        lambda cid: MagicMock() if cid == tt.TERRITORY_TRACKER_CHANNEL_ID else None
    )
    cog.client = client
    return cog


async def _run_tick(monkeypatch, old_data, new_data):
    saves = []
    exchanges = []
    monkeypatch.setattr(tt, "_read_territories_sync", lambda: old_data)
    monkeypatch.setattr(tt, "saveTerritoryData", lambda data: saves.append(data))
    monkeypatch.setattr(
        tt, "save_territory_exchanges", lambda changes: exchanges.append(changes)
    )

    async def fake_fetch():
        return new_data

    monkeypatch.setattr(tt, "getTerritoryData", fake_fetch)

    cog = _make_cog()
    await TerritoryTracker.territory_tracker.coro(cog)
    return saves, exchanges


@pytest.mark.asyncio
async def test_identical_snapshot_skips_write(monkeypatch):
    saves, exchanges = await _run_tick(monkeypatch, _snapshot(), _snapshot())
    assert saves == []
    assert exchanges == []


@pytest.mark.asyncio
async def test_ownership_change_writes_and_records_exchange(monkeypatch):
    old = _snapshot()
    new = _snapshot()
    new["Alpha Plains"] = _terr("Guild C", "CCC", acquired="2026-01-02T00:00:00Z")

    saves, exchanges = await _run_tick(monkeypatch, old, new)

    assert saves == [new]
    assert len(exchanges) == 1
    assert exchanges[0]["Alpha Plains"]["new"]["owner"] == "Guild C"


@pytest.mark.asyncio
async def test_missing_row_rewrites(monkeypatch):
    saves, _ = await _run_tick(monkeypatch, {}, _snapshot())
    assert saves == [_snapshot()]


@pytest.mark.asyncio
async def test_failed_fetch_writes_nothing(monkeypatch):
    saves, _ = await _run_tick(monkeypatch, _snapshot(), False)
    assert saves == []
