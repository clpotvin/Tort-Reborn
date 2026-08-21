"""
Test suite for the war build <-> Discord role sync (Tasks/sync_war_builds.py).

The database records which build a member runs; Discord records only the role
that build implies. The reconciler is the single writer in both directions, and
the gateway listener only flags members for it.

The bug this suite pins down: the listener used to write straight to the
database on every observed role delta, including the deltas caused by the
reconciler's own writes. The two halves then took turns undoing each other,
and because the database half's response to "role gone" is a DELETE, real
exec-assigned builds were destroyed on each pass.

1. Echo suppressor recognises our own writes and expires them
2. Consuming an echo is one-shot, so a human repeating it is still honoured
3. The listener ignores our own echo and never marks the member dirty
4. A genuine human edit is flagged for reconcile
5. The listener never writes to the database
6. Role/build planning is a plain set difference in both directions
7. Discord-side additions assign the default build for the role
8. Discord-side removals delete the role's builds and report what was lost
9. Unlinked members are left alone in both directions
10. The reconciler projects the database onto Discord
11. Members with no linked account keep their roles (no opinion != remove)
12. A missing war role object skips the tick instead of stripping the guild
13. Regression: a full add-then-echo cycle deletes nothing and converges
"""

import asyncio
import os
import sys

import discord

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Tasks import sync_war_builds as swb

UUID_A = "11111111-1111-4111-8111-111111111111"
UUID_B = "22222222-2222-4222-8222-222222222222"


# ── fakes ────────────────────────────────────────────────────────────────

class FakeRole:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"<Role {self.name}>"


class FakeMember:
    def __init__(self, member_id, roles, guild=None, name=None):
        self.id = member_id
        self.roles = list(roles)
        self.guild = guild
        self.display_name = name or f"member-{member_id}"
        self.added = []
        self.removed = []

    async def add_roles(self, *roles, reason=None):
        self.added.append({r.name for r in roles})
        self.roles.extend(roles)

    async def remove_roles(self, *roles, reason=None):
        names = {r.name for r in roles}
        self.removed.append(names)
        self.roles = [r for r in self.roles if r.name not in names]


class FakeGuild:
    def __init__(self, roles, members, chunked=True):
        self.id = swb.TAQ_GUILD_ID
        self.roles = roles
        self.members = members
        self.chunked = chunked
        for m in members:
            m.guild = self

    async def fetch_member(self, member_id):
        for m in self.members:
            if m.id == member_id:
                return m
        raise discord.NotFound(_FakeResponse(), "unknown member")


class _FakeResponse:
    status = 404
    reason = "Not Found"


class FakeClient:
    def __init__(self, guild):
        self._guild = guild

    def get_guild(self, guild_id):
        return self._guild


class Recorder:
    """Stands in for the module's blocking DB helpers."""

    def __init__(self, builds=None, links=None, defaults=None):
        # builds: {uuid: {db_role, ...}}
        self.builds = builds or {}
        # links: {uuid: discord_id_str}
        self.links = links or {}
        self.defaults = defaults or {"TANK": "guardian",
                                     "HEALER": "absolution",
                                     "DPS": "divzer"}
        self.added = []
        self.deleted = []

    def install(self, monkeypatch):
        monkeypatch.setattr(swb, "_fetch_state", self.fetch_state)
        monkeypatch.setattr(swb, "_get_default_build_key", self.default_key)
        monkeypatch.setattr(swb, "_add_member_build", self.add_build)
        monkeypatch.setattr(swb, "_remove_member_builds_by_role", self.remove_builds)
        return self

    def fetch_state(self):
        builds = {u: set(r) for u, r in self.builds.items()}
        uuid_to_discord = dict(self.links)
        discord_to_uuid = {d: u for u, d in self.links.items()}
        return builds, uuid_to_discord, discord_to_uuid

    def default_key(self, db_role):
        return self.defaults.get(db_role)

    def add_build(self, uuid, build_key, assigned_by="discord_sync"):
        self.added.append((uuid, build_key))
        for role, key in self.defaults.items():
            if key == build_key:
                self.builds.setdefault(uuid, set()).add(role)
        return True

    def remove_builds(self, uuid, db_role):
        if db_role not in self.builds.get(uuid, set()):
            return []
        self.builds[uuid].discard(db_role)
        self.deleted.append((uuid, db_role))
        return [(self.defaults[db_role], 1, 0)]


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _war_roles():
    return {n: FakeRole(n) for n in ("Tank", "DPS", "Healer")}


# ── 1-2: echo suppressor ─────────────────────────────────────────────────

def test_echo_recognises_our_own_write():
    echo = swb.EchoSuppressor()
    echo.expect(7, {"Tank", "DPS"})
    assert echo.consume(7, {"Tank", "DPS"}) == set()


def test_echo_reports_changes_we_did_not_make():
    echo = swb.EchoSuppressor()
    echo.expect(7, {"Tank"})
    assert echo.consume(7, {"Tank", "Healer"}) == {"Healer"}


def test_echo_expires():
    clock = FakeClock()
    echo = swb.EchoSuppressor(ttl=30, clock=clock)
    echo.expect(7, {"Tank"})
    clock.advance(31)
    assert echo.consume(7, {"Tank"}) == {"Tank"}


def test_echo_purge_drops_stale_entries():
    clock = FakeClock()
    echo = swb.EchoSuppressor(ttl=30, clock=clock)
    echo.expect(7, {"Tank"})
    clock.advance(31)
    echo.purge()
    assert len(echo) == 0


def test_echo_consumption_is_one_shot():
    """A human re-applying the same change must not be swallowed."""
    echo = swb.EchoSuppressor()
    echo.expect(7, {"Tank"})
    assert echo.consume(7, {"Tank"}) == set()
    assert echo.consume(7, {"Tank"}) == {"Tank"}


# ── 3-5: the listener ────────────────────────────────────────────────────

def _listener_cog(monkeypatch):
    recorder = Recorder().install(monkeypatch)
    cog = swb.SyncWarBuilds(client=None)
    return cog, recorder


def test_listener_ignores_our_own_echo(monkeypatch):
    cog, recorder = _listener_cog(monkeypatch)
    roles = _war_roles()
    guild = FakeGuild(list(roles.values()), [])
    before = FakeMember(7, [], guild=guild)
    after = FakeMember(7, [roles["Tank"]], guild=guild)

    cog.echo.expect(7, {"Tank"})
    asyncio.run(cog.on_member_update(before, after))

    assert cog.dirty == set()
    assert recorder.deleted == []


def test_listener_flags_human_edit(monkeypatch):
    cog, _ = _listener_cog(monkeypatch)
    roles = _war_roles()
    guild = FakeGuild(list(roles.values()), [])
    before = FakeMember(7, [roles["Tank"]], guild=guild)
    after = FakeMember(7, [], guild=guild)

    asyncio.run(cog.on_member_update(before, after))

    assert cog.dirty == {7}


def test_listener_never_writes_to_the_database(monkeypatch):
    """The regression: a role delta alone must not delete builds."""
    cog, recorder = _listener_cog(monkeypatch)
    recorder.builds = {UUID_A: {"TANK", "DPS", "HEALER"}}
    recorder.links = {UUID_A: "7"}
    roles = _war_roles()
    guild = FakeGuild(list(roles.values()), [])
    before = FakeMember(7, list(roles.values()), guild=guild)
    after = FakeMember(7, [], guild=guild)

    asyncio.run(cog.on_member_update(before, after))

    assert recorder.deleted == []
    assert recorder.added == []
    assert recorder.builds == {UUID_A: {"TANK", "DPS", "HEALER"}}


def test_listener_ignores_other_guilds(monkeypatch):
    cog, _ = _listener_cog(monkeypatch)
    roles = _war_roles()
    guild = FakeGuild(list(roles.values()), [])
    guild.id = swb.TAQ_GUILD_ID + 1
    before = FakeMember(7, [roles["Tank"]], guild=guild)
    after = FakeMember(7, [], guild=guild)

    asyncio.run(cog.on_member_update(before, after))

    assert cog.dirty == set()


# ── 6: planning ──────────────────────────────────────────────────────────

def test_plan_role_changes():
    add, remove = swb.plan_role_changes({"Tank"}, {"Tank", "DPS"})
    assert add == {"DPS"}
    assert remove == set()


def test_plan_build_changes():
    need, drop = swb.plan_build_changes({"Tank"}, {"Healer"})
    assert need == {"Tank"}
    assert drop == {"Healer"}


def test_roles_to_discord_names_drops_unknown():
    assert swb.roles_to_discord_names({"TANK", "BARD"}) == {"Tank"}


# ── 7-9: folding Discord edits into the database ────────────────────────

def test_discord_addition_assigns_default_build(monkeypatch):
    recorder = Recorder(builds={}, links={UUID_A: "7"}).install(monkeypatch)
    roles = _war_roles()
    member = FakeMember(7, [roles["Tank"]])
    guild = FakeGuild(list(roles.values()), [member])
    cog = swb.SyncWarBuilds(client=FakeClient(guild))

    changes = asyncio.run(cog._apply_discord_intent(guild, 7, recorder.fetch_state()))

    assert changes == 1
    assert recorder.added == [(UUID_A, "guardian")]


def test_discord_removal_deletes_builds(monkeypatch):
    recorder = Recorder(builds={UUID_A: {"TANK"}},
                        links={UUID_A: "7"}).install(monkeypatch)
    roles = _war_roles()
    member = FakeMember(7, [])
    guild = FakeGuild(list(roles.values()), [member])
    cog = swb.SyncWarBuilds(client=FakeClient(guild))

    changes = asyncio.run(cog._apply_discord_intent(guild, 7, recorder.fetch_state()))

    assert changes == 1
    assert recorder.deleted == [(UUID_A, "TANK")]


def test_unlinked_member_edit_is_ignored(monkeypatch):
    recorder = Recorder(builds={}, links={}).install(monkeypatch)
    roles = _war_roles()
    member = FakeMember(7, [roles["Tank"]])
    guild = FakeGuild(list(roles.values()), [member])
    cog = swb.SyncWarBuilds(client=FakeClient(guild))

    changes = asyncio.run(cog._apply_discord_intent(guild, 7, recorder.fetch_state()))

    assert changes == 0
    assert recorder.added == []
    assert recorder.deleted == []


# ── 10-12: the reconciler ────────────────────────────────────────────────

def test_reconciler_projects_database_onto_discord(monkeypatch):
    Recorder(builds={UUID_A: {"TANK"}}, links={UUID_A: "7"}).install(monkeypatch)
    roles = _war_roles()
    member = FakeMember(7, [roles["Healer"]])
    guild = FakeGuild(list(roles.values()), [member])
    cog = swb.SyncWarBuilds(client=FakeClient(guild))

    asyncio.run(cog._reconcile())

    assert member.added == [{"Tank"}]
    assert member.removed == [{"Healer"}]
    assert {r.name for r in member.roles} == {"Tank"}


def test_unlinked_member_keeps_roles(monkeypatch):
    """No database opinion must not be read as 'strip their roles'."""
    Recorder(builds={UUID_A: {"TANK"}}, links={UUID_A: "7"}).install(monkeypatch)
    roles = _war_roles()
    linked = FakeMember(7, [roles["Tank"]])
    stranger = FakeMember(99, [roles["Healer"]])
    guild = FakeGuild(list(roles.values()), [linked, stranger])
    cog = swb.SyncWarBuilds(client=FakeClient(guild))

    asyncio.run(cog._reconcile())

    assert stranger.removed == []
    assert {r.name for r in stranger.roles} == {"Healer"}


def test_missing_war_role_skips_tick(monkeypatch):
    Recorder(builds={}, links={UUID_A: "7"}).install(monkeypatch)
    partial = [FakeRole("Tank"), FakeRole("DPS")]  # no Healer
    member = FakeMember(7, [partial[0]])
    guild = FakeGuild(partial, [member])
    cog = swb.SyncWarBuilds(client=FakeClient(guild))

    asyncio.run(cog._reconcile())

    assert member.removed == []
    assert {r.name for r in member.roles} == {"Tank"}


def test_unchunked_cache_skips_tick(monkeypatch):
    Recorder(builds={}, links={UUID_A: "7"}).install(monkeypatch)
    roles = _war_roles()
    member = FakeMember(7, [roles["Tank"]])
    guild = FakeGuild(list(roles.values()), [member], chunked=False)
    cog = swb.SyncWarBuilds(client=FakeClient(guild))

    asyncio.run(cog._reconcile())

    assert member.removed == []


# ── 13: the oscillation regression ───────────────────────────────────────

def test_add_then_echo_deletes_nothing_and_converges(monkeypatch):
    """Reproduces the 2026-08-13 incident end to end.

    The reconciler grants roles from the database, Discord echoes each grant
    back over the gateway, and the listener sees the delta. Previously that
    echo was read as a human removing builds and the rows were deleted, so the
    next tick stripped the roles it had just handed out. Now the echo is
    recognised, nothing is deleted, and a second tick is a no-op.
    """
    recorder = Recorder(builds={UUID_A: {"TANK", "DPS", "HEALER"}},
                        links={UUID_A: "7"}).install(monkeypatch)
    roles = _war_roles()
    member = FakeMember(7, [], name="Kenji121")
    guild = FakeGuild(list(roles.values()), [member])
    cog = swb.SyncWarBuilds(client=FakeClient(guild))

    # Tick one: the database says three roles, Discord has none.
    asyncio.run(cog._reconcile())
    assert member.added == [{"Tank", "DPS", "Healer"}]

    # Discord echoes the grant back. This is what used to wipe the builds.
    before = FakeMember(7, [], guild=guild)
    after = FakeMember(7, list(roles.values()), guild=guild)
    asyncio.run(cog.on_member_update(before, after))

    assert cog.dirty == set()
    assert recorder.deleted == []
    assert recorder.builds == {UUID_A: {"TANK", "DPS", "HEALER"}}

    # Tick two: already in agreement, so nothing moves.
    asyncio.run(cog._reconcile())
    assert member.removed == []
    assert member.added == [{"Tank", "DPS", "Healer"}]
    assert {r.name for r in member.roles} == {"Tank", "DPS", "Healer"}


def test_human_removal_survives_a_reconcile(monkeypatch):
    """An officer pulling a role in Discord is honoured, not reverted."""
    recorder = Recorder(builds={UUID_A: {"TANK"}},
                        links={UUID_A: "7"}).install(monkeypatch)
    roles = _war_roles()
    member = FakeMember(7, [], name="Thundderr")  # officer already pulled Tank
    guild = FakeGuild(list(roles.values()), [member])
    cog = swb.SyncWarBuilds(client=FakeClient(guild))

    before = FakeMember(7, [roles["Tank"]], guild=guild)
    asyncio.run(cog.on_member_update(before, member))
    assert cog.dirty == {7}

    asyncio.run(cog._reconcile())

    assert recorder.deleted == [(UUID_A, "TANK")]
    assert member.added == []          # not handed back
    assert member.roles == []
