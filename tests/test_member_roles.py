"""Tests for Helpers/member_roles.py — the single source of truth for
membership role names (TAQ-51 / TAQ-67).

What matters here:

1. Removal restores the honorifics independently — Honored Fish and Retired
   Chief are separate honors; neither implies the other.
2. The removal list can never strip what removal itself just granted
   (Ex-Member, restored honorifics) — that invariant is what makes the
   restore safe to run in one pass.
3. The list matches the guild as it exists today: the new military block
   (⚬ Shelf … ⚬ ⚬ ⚬ ⚬ Abyss), HQ Team, and the renamed CONTRIBUTION header
   are present; the stale pre-rename spellings are gone.
4. Registration strips exactly the honorifics/visitor roles and records the
   honorific flags first.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Helpers import member_roles as mr


class FakeRole:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"<Role {self.name}>"


class FakeMember:
    def __init__(self, roles):
        self.roles = list(roles)


# ── removal planning ─────────────────────────────────────────────────────

def test_removal_adds_only_ex_member_without_honorifics():
    to_add, _ = mr.removal_role_names()
    assert to_add == [mr.EX_MEMBER_ROLE]


def test_removal_restores_honored_fish_alone():
    to_add, _ = mr.removal_role_names(was_honored_fish=True)
    assert to_add == [mr.EX_MEMBER_ROLE, mr.HONORED_FISH_ROLE]


def test_removal_restores_retired_chief_alone():
    # Retired Chief does not drag Honored Fish along: separate honors.
    to_add, _ = mr.removal_role_names(was_retired_chief=True)
    assert to_add == [mr.EX_MEMBER_ROLE, mr.RETIRED_CHIEF_ROLE]


def test_removal_restores_both_when_both_were_held():
    to_add, _ = mr.removal_role_names(was_honored_fish=True, was_retired_chief=True)
    assert to_add == [mr.EX_MEMBER_ROLE, mr.HONORED_FISH_ROLE, mr.RETIRED_CHIEF_ROLE]


def test_removal_never_strips_what_it_grants():
    to_add, to_remove = mr.removal_role_names(True, True)
    assert not set(to_add) & set(to_remove)
    # And the static list itself can never contain the keeps.
    for keep in (mr.EX_MEMBER_ROLE, mr.HONORED_FISH_ROLE, mr.RETIRED_CHIEF_ROLE):
        assert keep not in mr.MEMBER_REMOVE_ROLES


def test_removal_list_covers_current_military_block():
    for name in ['⚬ Shelf', '⚬ ⚬ Slope', '⚬ ⚬ ⚬ Rise', '⚬ ⚬ ⚬ ⚬ Abyss',
                 'HQ Team', 'DPS', 'Tank', 'Healer', 'EcoFish',
                 'War Trainer', 'Territory Munching', 'Soloer']:
        assert name in mr.MEMBER_REMOVE_ROLES, name


def test_removal_list_uses_renamed_contribution_header():
    assert mr.CONTRIBUTION_HEADER in mr.MEMBER_REMOVE_ROLES
    assert not mr.CONTRIBUTION_HEADER.startswith('🏆')


def test_removal_list_dropped_stale_role_names():
    # Roles that no longer exist in the guild; keeping them would only hide
    # future name-rot behind silent no-ops.
    stale = {'🏹Spearhead', '⚠️Standby', '🗡️FFA', 'Orca', 'War News'}
    assert not stale & set(mr.MEMBER_REMOVE_ROLES)


def test_removal_list_has_no_duplicates():
    assert len(mr.MEMBER_REMOVE_ROLES) == len(set(mr.MEMBER_REMOVE_ROLES))


# ── registration planning ────────────────────────────────────────────────

def test_registration_strips_honorifics_and_visitor_roles():
    _, to_remove = mr.registration_role_names('Starfish')
    assert set(to_remove) == {mr.LAND_CRAB_ROLE, mr.HONORED_FISH_ROLE,
                              mr.RETIRED_CHIEF_ROLE, mr.EX_MEMBER_ROLE}


def test_registration_adds_membership_rank_and_headers():
    to_add, _ = mr.registration_role_names('Piranha')
    assert mr.MEMBER_ROLE in to_add
    assert mr.TAQ_TAG_ROLE in to_add
    assert 'Piranha' in to_add
    for header in mr.REGISTRATION_HEADER_ROLES:
        assert header in to_add
    assert mr.CONTRIBUTION_HEADER in to_add


def test_honorific_flags_read_from_role_names():
    assert mr.honorific_flags(['Member', 'DPS']) == (False, False)
    assert mr.honorific_flags(['Honored Fish']) == (True, False)
    assert mr.honorific_flags(['Retired Chief']) == (False, True)
    assert mr.honorific_flags(['Honored Fish', 'Retired Chief']) == (True, True)


# ── role resolution ──────────────────────────────────────────────────────

def test_resolve_roles_skips_names_the_guild_lacks():
    guild_roles = [FakeRole('Member'), FakeRole('DPS')]
    roles = mr.resolve_roles(guild_roles, ['Member', 'Ghost Role', 'DPS'])
    assert [r.name for r in roles] == ['Member', 'DPS']


def test_resolve_roles_present_filter():
    member_role = FakeRole('Member')
    dps_role = FakeRole('DPS')
    ex_role = FakeRole('Ex-Member')
    guild_roles = [member_role, dps_role, ex_role]
    member = FakeMember([member_role])

    held = mr.resolve_roles(guild_roles, ['Member', 'DPS', 'Ex-Member'],
                            member=member, present=True)
    assert held == [member_role]

    missing = mr.resolve_roles(guild_roles, ['Member', 'DPS', 'Ex-Member'],
                               member=member, present=False)
    assert missing == [dps_role, ex_role]
