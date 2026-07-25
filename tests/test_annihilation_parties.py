import asyncio
import datetime

import pytest

from Helpers.annihilation_parties import (
    BOARD_CLOSE_DELAY,
    AnnihilationPartyError,
    build_board_embeds,
    choose_available_slot,
    normalize_build,
    normalize_ign,
    normalize_notes,
    normalize_world,
)
from Tasks.annihilation_parties import PartyEntryModal, _party_options

UTC = datetime.timezone.utc


def _member(
    member_id: int,
    ign: str,
    *,
    leader: bool = False,
    party_number: int = 1,
) -> dict:
    joined_at = datetime.datetime(2026, 7, 24, 12, member_id, tzinfo=UTC)
    return {
        "id": member_id,
        "discord_id": 1000 + member_id,
        "ign": ign,
        "uuid": None,
        "party_number": party_number,
        "slot_number": member_id,
        "build": "Labyrinth Trapper",
        "combat_role": None,
        "bringing_scrolls": member_id % 2 == 0,
        "notes": "Ready",
        "party_joined_at": joined_at,
        "created_at": joined_at,
        "updated_at": joined_at,
        "is_leader": leader,
    }


def _event(*, closed: bool = False) -> dict:
    schedule = datetime.datetime.now(UTC).replace(microsecond=0) + datetime.timedelta(
        hours=1
    )
    parties = {
        party_number: {
            "party_number": party_number,
            "world": None,
            "members": [],
        }
        for party_number in range(1, 6)
    }
    return {
        "id": 7,
        "schedule_at": schedule,
        "closes_at": schedule + BOARD_CLOSE_DELAY,
        "guild_id": 1,
        "channel_id": 2,
        "message_id": 3,
        "thread_id": 4,
        "status": "closed" if closed else "active",
        "closed_at": schedule + BOARD_CLOSE_DELAY if closed else None,
        "discord_closed_at": None,
        "parties": parties,
    }


@pytest.mark.parametrize(
    ("occupied", "expected"),
    [
        ([], 1),
        ([1, 2, 4], 3),
        (range(1, 11), None),
    ],
)
def test_choose_available_slot(occupied, expected):
    assert choose_available_slot(occupied) == expected


@pytest.mark.parametrize("ign", ["A", "Player_Name", "abc123", "SixteenCharsHere"])
def test_normalize_ign_accepts_minecraft_names(ign):
    assert normalize_ign(ign) == ign


@pytest.mark.parametrize("ign", ["", "has space", "punctuation!", "x" * 17])
def test_normalize_ign_rejects_invalid_names(ign):
    with pytest.raises(AnnihilationPartyError):
        normalize_ign(ign)


def test_normalizers_trim_and_validate_entry_text():
    assert normalize_build("  Laby   Trapper  ") == "Laby Trapper"
    assert normalize_notes("  bringing   potions ") == "bringing potions"
    assert normalize_notes("   ") is None
    assert normalize_world(" eu12 ") == "EU12"


@pytest.mark.parametrize("world", ["world 1", "WC", "123", "EU1234"])
def test_normalize_world_rejects_invalid_worlds(world):
    with pytest.raises(AnnihilationPartyError):
        normalize_world(world)


def test_board_renders_first_member_as_leader_and_successor_after_leave():
    event = _event()
    first = _member(1, "First", leader=True)
    second = _member(2, "Second")
    event["parties"][1]["members"] = [first, second]
    event["parties"][1]["world"] = "WC12"

    embeds = build_board_embeds(event)
    assert embeds[0].title == "Prelude to Annihilation"
    assert "Hateful echoes erupt from the Portal." in embeds[0].description
    assert "Sign-ups are open!" in embeds[0].description
    assert "Prepare to defend the province" in embeds[0].description
    assert embeds[0].colour.value == 0xE00000
    party_description = embeds[1].description
    assert "👑" in party_description.splitlines()[0]
    assert "<@1001>" in party_description.splitlines()[0]
    assert "First" not in party_description
    assert embeds[1].title == "Party 1: 2 / 10"
    assert embeds[1].fields[0].value == "WC12"
    assert embeds[1].fields[1].value == "<@1001>"

    event["parties"][1]["members"] = [
        {**second, "is_leader": True},
    ]
    embeds = build_board_embeds(event)
    assert embeds[1].fields[1].value == "<@1002>"
    assert "👑" in embeds[1].description.splitlines()[0]


def test_board_turns_gray_after_start_even_before_close_loop_finalizes():
    event = _event()
    event["schedule_at"] = datetime.datetime.now(UTC) - datetime.timedelta(minutes=1)
    event["closes_at"] = event["schedule_at"]

    embeds = build_board_embeds(event)

    assert embeds[0].title == "Prelude to Annihilation"
    assert "Sign-ups are closed!" in embeds[0].description
    assert embeds[0].colour.value == 0x747F8D


def test_empty_parties_are_hidden_from_board():
    event = _event()
    embeds = build_board_embeds(event)
    assert len(embeds) == 1


def test_closed_board_copy_changes_and_retains_party_snapshot():
    event = _event(closed=True)
    event["parties"][2]["members"] = [
        _member(1, "Archived", leader=True, party_number=2)
    ]
    embeds = build_board_embeds(event)
    assert embeds[0].title == "Prelude to Annihilation"
    assert "Sign-ups are closed!" in embeds[0].description
    assert embeds[1].title == "Party 2: 1 / 10"
    assert "<@1001>" in embeds[1].description
    assert "Archived" not in embeds[1].description


def test_full_board_stays_within_discords_combined_embed_limit():
    event = _event()
    next_id = 1
    for party_number in range(1, 6):
        members = []
        for _ in range(10):
            member = _member(
                next_id,
                "X" * 16,
                leader=not members,
                party_number=party_number,
            )
            member["discord_id"] = 9_999_999_999_999_999_999
            member["build"] = "B" * 50
            member["notes"] = "N" * 50
            members.append(member)
            next_id += 1
        event["parties"][party_number]["members"] = members

    embeds = build_board_embeds(event)
    character_count = 0
    for embed in embeds:
        character_count += len(embed.title or "")
        character_count += len(embed.description or "")
        character_count += len(embed.footer.text if embed.footer else "")
        for field in embed.fields:
            character_count += len(field.name) + len(field.value)

    assert character_count <= 6000


def test_full_parties_are_not_offered_to_new_entries():
    event = _event()
    event["parties"][1]["members"] = [
        _member(index, f"Player{index}") for index in range(1, 11)
    ]
    values = [option.value for option in _party_options(event)]
    assert "1" not in values
    assert values == ["2", "3", "4", "5"]


def test_current_full_party_remains_available_when_modifying():
    event = _event()
    event["parties"][1]["members"] = [
        _member(index, f"Player{index}") for index in range(1, 11)
    ]
    values = [option.value for option in _party_options(event, current_party=1)]
    assert values == ["1", "2", "3", "4", "5"]


def test_pycord_28_modal_contains_native_selects():
    async def build_modal():
        event = _event()
        modal = PartyEntryModal(
            None,
            event,
            member=None,
            actor_can_manage=False,
        )
        return modal

    modal = asyncio.run(build_modal())
    assert len(modal.children) == 5
    assert modal.get_item("party").options
    assert modal.get_item("combat_role") is None
    special_role = modal.get_item("special_role")
    assert special_role.required is False
    assert special_role.min_values == 0
    assert [option.label for option in special_role.options] == [
        "Healer",
        "Guardian",
    ]
    assert [option.value for option in special_role.options] == [
        "healer",
        "guardian",
    ]
    assert not any(option.default for option in special_role.options)
    assert modal.get_item("scrolls").options
    assert any(option.default for option in modal.get_item("scrolls").options)
    assert modal.get_item("ign") is None
