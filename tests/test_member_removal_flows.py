"""End-to-end worked examples for the TAQ-51 / TAQ-67 member flows.

These drive the *real* code — the `/reset_roles` slash command callback, the
"Member | Remove" user command callback, and the promotion queue's
`_do_remove` — against fake Discord objects and a fake DB, using a role
inventory copied from the prod guild. Each scenario asserts the member's
exact final role set, not just deltas, so an over- or under-strip fails
loudly.

Worked examples:

1. TAQ-51's report verbatim: brenzoned held Honored Fish, rejoined as
   Manatee, was later removed — and must end up with Honored Fish again.
2. A Retired Chief does the same round trip and gets Retired Chief back —
   and only that; the honorifics are independent.
3. A veteran holding the full guild stack (ranks, headers, new military
   block, staff roles, contribution awards) is stripped down to exactly
   Ex-Member + restored honorific + their non-guild roles.
4. The promotion queue reads the honorific record *before* deleting the
   discord_links row it lives in.
5. No discord_links row -> plain Ex-Member, no restore, no crash.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Helpers import member_roles as mr
from Helpers.functions import determine_starting_rank


# ── fakes ────────────────────────────────────────────────────────────────

class FakeRole:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"<Role {self.name!r}>"


class FakePermissions:
    manage_roles = True


class FakeMember:
    def __init__(self, member_id, role_names, guild):
        self.id = member_id
        self.guild = guild
        self.roles = [guild.role(n) for n in role_names]
        self.name = f"user-{member_id}"
        self.guild_permissions = FakePermissions()
        self.nick_edits = []

    async def add_roles(self, *roles, reason=None, atomic=True):
        for r in roles:
            assert r not in self.roles, f"double-add of {r}"
            self.roles.append(r)

    async def remove_roles(self, *roles, reason=None, atomic=True):
        for r in roles:
            assert r in self.roles, f"removing role not held: {r}"
            self.roles.remove(r)

    async def edit(self, nick=None):
        self.nick_edits.append(nick)

    @property
    def role_names(self):
        return {r.name for r in self.roles}


class FakeGuild:
    """Role inventory mirroring the prod guild (relevant subset)."""

    def __init__(self):
        names = [
            '@everyone', mr.MEMBER_ROLE, mr.TAQ_TAG_ROLE, mr.LAND_CRAB_ROLE,
            mr.EX_MEMBER_ROLE, mr.HONORED_FISH_ROLE, mr.RETIRED_CHIEF_ROLE,
            # rank pairs
            'Starfish', '☆Reef', 'Manatee', '★Coastal Waters', 'Piranha',
            '★★ Azure Ocean', 'Angler', 'Swordfish', '★☆☆ Blue Sea',
            'Hammerhead', '★★☆Deep Sea', 'Sailfish', '★★★Dark Sea',
            'Dolphin', 'Narwhal', '★★★★Abyss Waters',
            # headers
            mr.RANKS_HEADER, mr.PROFESSIONS_HEADER, mr.COSMETIC_HEADER,
            mr.CONTRIBUTION_HEADER, mr.MILITARY_HEADER,
            # military + staff + contribution awards
            *mr.MILITARY_ROLES, *mr.STAFF_ROLES, *mr.CONTRIBUTION_ROLES,
            # non-guild roles ex-members are allowed to keep
            'Merman', 'Europe', 'Giveaways', 'Sea Pickle - Booster',
            'Tortoise - Community',
        ]
        self.roles = [FakeRole(n) for n in dict.fromkeys(names)]
        self._by_name = {r.name: r for r in self.roles}

    def role(self, name):
        return self._by_name[name]


class FakeDB:
    """Yields queued fetchone() results in order; records every statement."""

    def __init__(self, fetchone_results):
        self._results = list(fetchone_results)
        self.executed = []
        self.cursor = self
        self.connection = self

    def connect(self):
        pass

    def close(self):
        pass

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self._results.pop(0)

    def commit(self):
        pass


class FakeInteractionMessage:
    """Stands in for the ApplicationContext of the /reset_roles slash command
    and the Interaction of the Member | Remove user command."""

    def __init__(self, invoker_id, guild):
        self.guild = guild
        self.user = FakeMember(invoker_id, [], guild)
        self.author = self.user
        self.interaction = self
        self.responses = []

    async def defer(self, ephemeral=False):
        pass

    async def respond(self, *args, **kwargs):
        self.responses.append((args, kwargs))

    def last_embed(self):
        args, kwargs = self.responses[-1]
        return kwargs.get('embed') or args[0]


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def simulate_registration(member):
    """Apply the shared registration plan the way all three flows do."""
    was_hf, was_rc = mr.honorific_flags(r.name for r in member.roles)
    starting_rank = determine_starting_rank(member)
    to_add, to_remove = mr.registration_role_names(starting_rank)
    run(member.add_roles(*mr.resolve_roles(member.guild.roles, to_add,
                                           member=member, present=False)))
    run(member.remove_roles(*mr.resolve_roles(member.guild.roles, to_remove,
                                              member=member, present=True)))
    return starting_rank, was_hf, was_rc


# ── the three real removal entry points ──────────────────────────────────

def remove_via_slash_command(member, invoker, db, monkeypatch):
    """Drive the actual /reset_roles callback (Commands/reset_roles.py)."""
    import Commands.reset_roles as cmd_mod
    monkeypatch.setattr(cmd_mod, 'DB', lambda: db)
    cog = cmd_mod.ResetRolesCommand(client=None)
    ctx = FakeInteractionMessage(invoker.id, member.guild)
    run(cog.reset_roles.callback(cog, ctx, member))
    return ctx


def remove_via_user_command(member, invoker, db, monkeypatch):
    """Drive the actual Member | Remove callback (UserCommands/reset_roles.py)."""
    import UserCommands.reset_roles as ucmd_mod
    monkeypatch.setattr(ucmd_mod, 'DB', lambda: db)
    cog = ucmd_mod.ResetRoles(client=None)
    interaction = FakeInteractionMessage(invoker.id, member.guild)
    run(cog.reset_roles.callback(cog, interaction, member))
    return interaction


def remove_via_promotion_queue(member, flags_row, monkeypatch):
    """Drive the actual _do_remove (Tasks/promotion_queue_processor.py)."""
    import Tasks.promotion_queue_processor as pq_mod
    calls = []

    def fake_flags(discord_id):
        calls.append('flags')
        return (bool(flags_row[0]), bool(flags_row[1])) if flags_row else (False, False)

    def fake_delete(discord_id):
        calls.append('delete')

    proc = pq_mod.PromotionQueueProcessor(client=None)
    monkeypatch.setattr(proc, '_lookup_honorific_flags', fake_flags)
    monkeypatch.setattr(proc, '_remove_from_discord_links', fake_delete)
    entry = {'queued_by_ign': 'QueuerIGN'}
    run(proc._do_remove(entry, member, member.guild))
    return calls


# ── worked example 1: TAQ-51's report (brenzoned) ────────────────────────

def test_honored_fish_round_trip_via_slash_command(monkeypatch):
    guild = FakeGuild()
    # Ex-member state before rejoining: honored, plus personal roles.
    brenzoned = FakeMember(101, [mr.EX_MEMBER_ROLE, mr.HONORED_FISH_ROLE,
                                 'Merman', 'Europe'], guild)

    # Rejoins the guild: Honored Fish -> starts as Manatee.
    starting_rank, was_hf, was_rc = simulate_registration(brenzoned)
    assert starting_rank == 'Manatee'
    assert (was_hf, was_rc) == (True, False)  # what registration records in the DB
    assert brenzoned.role_names == {
        mr.MEMBER_ROLE, mr.TAQ_TAG_ROLE, 'Manatee', '★Coastal Waters',
        *mr.REGISTRATION_HEADER_ROLES, 'Merman', 'Europe',
    }

    # Later removed by an HR (initiator Narwhal, target rank Manatee).
    db = FakeDB([('Narwhal',), ('Manatee', True, False)])
    ctx = remove_via_slash_command(brenzoned, FakeMember(1, [], guild), db, monkeypatch)

    # TAQ-51: Honored Fish is back; every guild role is gone; personal roles kept.
    assert brenzoned.role_names == {mr.EX_MEMBER_ROLE, mr.HONORED_FISH_ROLE,
                                    'Merman', 'Europe'}
    assert brenzoned.nick_edits == ['']
    assert 'Honored Fish' in ctx.last_embed().description


# ── worked example 2: Retired Chief, restored independently ──────────────

def test_retired_chief_round_trip_via_user_command(monkeypatch):
    guild = FakeGuild()
    chief = FakeMember(102, [mr.RETIRED_CHIEF_ROLE, 'Tortoise - Community'], guild)

    starting_rank, was_hf, was_rc = simulate_registration(chief)
    assert starting_rank == 'Piranha'
    assert (was_hf, was_rc) == (False, True)
    assert chief.role_names == {
        mr.MEMBER_ROLE, mr.TAQ_TAG_ROLE, 'Piranha', '★★ Azure Ocean',
        *mr.REGISTRATION_HEADER_ROLES, 'Tortoise - Community',
    }

    # Member | Remove: initiator row, then target row (rank, uuid, hf, rc).
    db = FakeDB([('Narwhal',), ('Piranha', 'some-uuid', False, True)])
    interaction = remove_via_user_command(chief, FakeMember(1, [], guild), db, monkeypatch)

    # Retired Chief restored; Honored Fish NOT implied (user decision on TAQ-67).
    assert chief.role_names == {mr.EX_MEMBER_ROLE, mr.RETIRED_CHIEF_ROLE,
                                'Tortoise - Community'}
    assert chief.nick_edits == ['']
    assert 'Retired Chief' in interaction.last_embed().description
    assert 'Honored Fish' not in interaction.last_embed().description


# ── worked example 3: full guild stack stripped via the promotion queue ──

def test_full_stack_veteran_removed_via_promotion_queue(monkeypatch):
    guild = FakeGuild()
    veteran = FakeMember(103, [
        mr.MEMBER_ROLE, mr.TAQ_TAG_ROLE,
        'Narwhal', '★★★★Abyss Waters', 'Dolphin', '★★★Dark Sea',
        mr.RANKS_HEADER, mr.PROFESSIONS_HEADER, mr.COSMETIC_HEADER,
        mr.CONTRIBUTION_HEADER, mr.MILITARY_HEADER,
        '⚬ Shelf', '⚬ ⚬ Slope', 'War Trainer', 'Territory Munching',
        'HQ Team', 'DPS', 'Tank', 'Healer', 'EcoFish', 'Soloer',
        'Event Team Manager', 'Shell Manager',
        'Noobwhal - #1 XP contributed', '#1 - Shells',
        'Raidfish (Graid Event Top #5)',
        'Sea Pickle - Booster', 'Merman',       # non-guild: must survive
    ], guild)

    calls = remove_via_promotion_queue(veteran, (True, False), monkeypatch)

    assert veteran.role_names == {mr.EX_MEMBER_ROLE, mr.HONORED_FISH_ROLE,
                                  'Sea Pickle - Booster', 'Merman'}
    assert veteran.nick_edits == ['']
    # The honorific record must be read before the discord_links row is deleted.
    assert calls == ['flags', 'delete']


# ── promotion queue edge cases ───────────────────────────────────────────

def test_promotion_queue_remove_without_link_row(monkeypatch):
    guild = FakeGuild()
    member = FakeMember(104, [mr.MEMBER_ROLE, 'Starfish', '☆Reef',
                              mr.RANKS_HEADER, 'Giveaways'], guild)

    remove_via_promotion_queue(member, None, monkeypatch)

    # No record -> no restore, just Ex-Member; non-guild role kept.
    assert member.role_names == {mr.EX_MEMBER_ROLE, 'Giveaways'}


def test_promotion_queue_remove_is_idempotent(monkeypatch):
    guild = FakeGuild()
    member = FakeMember(105, [mr.MEMBER_ROLE, 'Manatee'], guild)

    remove_via_promotion_queue(member, (True, False), monkeypatch)
    first = set(member.role_names)
    # Running removal again (e.g. website retry) must change nothing and not
    # crash on already-held Ex-Member/Honored Fish or already-removed roles.
    remove_via_promotion_queue(member, (True, False), monkeypatch)
    assert member.role_names == first == {mr.EX_MEMBER_ROLE, mr.HONORED_FISH_ROLE}


# ── slash command edge cases ─────────────────────────────────────────────

def test_slash_removal_of_unlinked_target_still_strips(monkeypatch):
    # Commands/reset_roles.py proceeds when the target has no discord_links
    # row (rank gate skipped): strip everything, no restore.
    guild = FakeGuild()
    member = FakeMember(106, [mr.MEMBER_ROLE, mr.TAQ_TAG_ROLE, 'Starfish',
                              '☆Reef', 'DPS', 'Europe'], guild)
    db = FakeDB([('Narwhal',), None])
    remove_via_slash_command(member, FakeMember(1, [], guild), db, monkeypatch)

    assert member.role_names == {mr.EX_MEMBER_ROLE, 'Europe'}


def test_slash_removal_blocked_for_equal_rank(monkeypatch):
    guild = FakeGuild()
    member = FakeMember(107, [mr.MEMBER_ROLE, 'Narwhal'], guild)
    db = FakeDB([('Narwhal',), ('Narwhal', False, False)])
    ctx = remove_via_slash_command(member, FakeMember(1, [], guild), db, monkeypatch)

    # Rank gate: nothing changed, permission-denied response sent.
    assert member.role_names == {mr.MEMBER_ROLE, 'Narwhal'}
    assert 'Permission denied' in ctx.last_embed().title
