import asyncio
import datetime
from pathlib import Path

import discord
from discord.ext import commands, tasks

from Helpers.annihilation_parties import (
    PARTY_COUNT,
    PARTY_SIZE,
    AnnihilationPartyError,
    add_member,
    build_board_embeds,
    close_due_events,
    ensure_event,
    get_event,
    get_event_by_message,
    get_linked_account,
    get_unfinalized_closed_events,
    mark_discord_closed,
    remove_member,
    set_board_message,
    set_board_thread,
    set_party_world,
    update_member,
    utc_now,
)
from Helpers.logger import ERROR, SUCCESS, WARN, log
from Helpers.variables import (
    ANNIHILATION_ANNOUNCEMENT_CHANNEL_ID,
    HOME_GUILD_IDS,
)

BOARD_ICON_PATH = Path("images/annihilation/prelude_to_annihilation.png")
BOARD_ICON_FILENAME = "prelude_to_annihilation.png"

def _is_manager(interaction: discord.Interaction) -> bool:
    permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(permissions and permissions.manage_roles)


def _party_options(
    event: dict, current_party: int | None = None
) -> list[discord.SelectOption]:
    options = []
    for party_number in range(1, PARTY_COUNT + 1):
        count = len(event["parties"][party_number]["members"])
        if count >= PARTY_SIZE and party_number != current_party:
            continue
        world = event["parties"][party_number].get("world")
        suffix = f" • {world}" if world else ""
        options.append(
            discord.SelectOption(
                label=f"Party {party_number} ({count}/{PARTY_SIZE}){suffix}",
                value=str(party_number),
                default=party_number == current_party,
            )
        )
    return options


def _special_role_options(role: str | None = None) -> list[discord.SelectOption]:
    role_names = {
        "healer": ("❤️‍🩹", "Healer"),
        "guardian": ("🛡️", "Guardian"),
    }
    return [
        discord.SelectOption(
            label=role_name,
            value=role_id,
            emoji=emoji,
            default=role_id == role,
        )
        for role_id, (emoji, role_name) in role_names.items()
    ]


def _scroll_options(bringing_scrolls: bool = False) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label="No scrolls",
            value="no",
            default=not bringing_scrolls,
        ),
        discord.SelectOption(
            label="Bringing scrolls",
            value="yes",
            default=bringing_scrolls,
        ),
    ]


def _member_from_event(event: dict, member_id: int) -> dict | None:
    for party in event["parties"].values():
        for member in party["members"]:
            if member["id"] == member_id:
                return member
    return None


def _member_for_discord_in_event(event: dict, discord_id: int) -> dict | None:
    for party in event["parties"].values():
        for member in party["members"]:
            if member["discord_id"] == discord_id:
                return member
    return None


class PartyEntryModal(discord.ui.DesignerModal):
    def __init__(
        self,
        cog: "AnnihilationParties",
        event: dict,
        *,
        member: dict | None,
        actor_can_manage: bool,
    ):
        self.cog = cog
        self.event_id = event["id"]
        self.member_id = member["id"] if member else None
        self.actor_can_manage = actor_can_manage

        build = discord.ui.Label("Build").set_input_text(
            custom_id="build",
            placeholder="e.g. Labyrinth Trapper",
            min_length=1,
            max_length=50,
            value=member["build"] if member else None,
        )
        party = discord.ui.Label("Party").set_select(
            custom_id="party",
            options=_party_options(
                event,
                member["party_number"] if member else None,
            ),
        )
        special_role = discord.ui.Label("Special Role").set_select(
            custom_id="special_role",
            placeholder="Optional",
            min_values=0,
            options=_special_role_options(member["combat_role"] if member else None),
            required=False,
        )
        scrolls = discord.ui.Label("Scrolls").set_select(
            custom_id="scrolls",
            options=_scroll_options(member["bringing_scrolls"] if member else False),
        )
        notes = discord.ui.Label("Additional information").set_input_text(
            custom_id="notes",
            placeholder="Optional notes for your party",
            max_length=50,
            required=False,
            value=member.get("notes") if member else None,
        )
        super().__init__(
            build,
            party,
            special_role,
            scrolls,
            notes,
            title="Modify party entry" if member else "Join Annihilation party",
            timeout=15 * 60,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        special_role_values = self.get_item("special_role").values
        await self.cog.submit_entry(
            interaction,
            event_id=self.event_id,
            member_id=self.member_id,
            actor_can_manage=self.actor_can_manage,
            build=self.get_item("build").value,
            party_number=int(self.get_item("party").values[0]),
            combat_role=special_role_values[0] if special_role_values else None,
            bringing_scrolls=self.get_item("scrolls").values[0] == "yes",
            notes=self.get_item("notes").value,
        )


class WorldModal(discord.ui.DesignerModal):
    def __init__(
        self,
        cog: "AnnihilationParties",
        event_id: int,
        party_number: int,
        current_world: str | None,
        can_manage: bool,
    ):
        self.cog = cog
        self.event_id = event_id
        self.party_number = party_number
        self.can_manage = can_manage
        world = discord.ui.Label(f"Party {party_number} world").set_input_text(
            custom_id="world",
            placeholder="e.g. WC12, EU3, NA8, or AS2",
            min_length=2,
            max_length=8,
            value=current_world or None,
        )
        super().__init__(world, title="Change party world", timeout=10 * 60)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.cog.change_world(
            interaction,
            event_id=self.event_id,
            party_number=self.party_number,
            world=self.get_item("world").value,
            can_manage=self.can_manage,
        )


class ConfirmRemovalView(discord.ui.View):
    def __init__(
        self,
        cog: "AnnihilationParties",
        invoker_id: int,
        event_id: int,
        member: dict,
        can_manage: bool,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.invoker_id = invoker_id
        self.event_id = event_id
        self.member = member
        self.can_manage = can_manage

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.invoker_id:
            return True
        await interaction.response.send_message(
            "Cooked idk how this happened",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Leave party", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer(ephemeral=True)
        self.stop()
        await self.cog.remove_entry(
            interaction,
            event_id=self.event_id,
            member_id=self.member["id"],
            can_manage=self.can_manage,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction,
    ):
        self.stop()
        await interaction.response.edit_message(
            content="Party removal cancelled",
            view=None,
        )


class StaffMemberPickerView(discord.ui.View):
    def __init__(
        self,
        cog: "AnnihilationParties",
        invoker_id: int,
        event: dict,
        party_number: int,
        action: str,
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.invoker_id = invoker_id
        self.event = event
        self.event_id = event["id"]
        self.action = action

        members = event["parties"][party_number]["members"]
        select = discord.ui.Select(
            placeholder="Choose a party member",
            options=[
                discord.SelectOption(
                    label=member["ign"],
                    description=f"Party {party_number}",
                    value=str(member["id"]),
                )
                for member in members
            ],
        )
        select.callback = self._selected
        self.add_item(select)

    async def _selected(self, interaction: discord.Interaction):
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "Cooked idk how this happened",
                ephemeral=True,
            )
            return

        member_id = int(interaction.data["values"][0])
        event = self.cog.active_event_snapshot(self.event_id) or self.event
        member = _member_from_event(event, member_id)
        if (
            event["status"] != "active"
            or event["closes_at"] <= utc_now()
                or not member
        ):
            await interaction.response.send_message(
                "That entry is no longer available",
                ephemeral=True,
            )
            return

        if self.action == "modify":
            await interaction.response.send_modal(
                PartyEntryModal(
                    self.cog,
                    event,
                    member=member,
                    actor_can_manage=True,
                )
            )
            return

        await interaction.response.edit_message(
            content=f"Remove **{member['ign']}** from Party {member['party_number']}?",
            view=ConfirmRemovalView(
                self.cog,
                self.invoker_id,
                self.event_id,
                member,
                can_manage=True,
            ),
        )


class StaffPartyPickerView(discord.ui.View):
    def __init__(
        self,
        cog: "AnnihilationParties",
        invoker_id: int,
        event: dict,
        action: str,
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.invoker_id = invoker_id
        self.event = event
        self.event_id = event["id"]
        self.action = action

        options = []
        for party_number, party in event["parties"].items():
            if not party["members"]:
                continue
            options.append(
                discord.SelectOption(
                    label=f"Party {party_number}",
                    description=(
                        f"{len(party['members'])}/{PARTY_SIZE} members"
                        + (f" • {party['world']}" if party.get("world") else "")
                    ),
                    value=str(party_number),
                )
            )
        select = discord.ui.Select(
            placeholder="Choose a party",
            options=options,
        )
        select.callback = self._selected
        self.add_item(select)

    async def _selected(self, interaction: discord.Interaction):
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "Cooked idk how this happened",
                ephemeral=True,
            )
            return

        party_number = int(interaction.data["values"][0])
        event = self.cog.active_event_snapshot(self.event_id) or self.event
        if event["status"] != "active" or event["closes_at"] <= utc_now():
            await interaction.response.send_message(
                "Sign-ups for this Annihilation event are closed",
                ephemeral=True,
            )
            return

        if self.action == "world":
            await interaction.response.send_modal(
                WorldModal(
                    self.cog,
                    self.event_id,
                    party_number,
                    event["parties"][party_number].get("world"),
                    can_manage=True,
                )
            )
            return

        if not event["parties"][party_number]["members"]:
            await interaction.response.edit_message(
                content="That party no longer has any entries",
                view=None,
            )
            return

        await interaction.response.edit_message(
            content=f"Choose an entry from Party {party_number}:",
            view=StaffMemberPickerView(
                self.cog,
                self.invoker_id,
                event,
                party_number,
                self.action,
            ),
        )


class AnnihilationPartyView(discord.ui.View):
    def __init__(self, cog: "AnnihilationParties"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Join party",
        emoji="⚔️",
        style=discord.ButtonStyle.success,
        custom_id="annihilation_party:join",
    )
    async def join(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction,
    ):
        event = await self.cog.event_for_interaction(interaction)
        if not event:
            return
        if not _party_options(event):
            await interaction.response.send_message(
                "The set annihilation party limit has been reached",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            PartyEntryModal(
                self.cog,
                event,
                member=None,
                actor_can_manage=False,
            )
        )

    @discord.ui.button(
        label="Modify entry",
        emoji="🛠️",
        style=discord.ButtonStyle.primary,
        custom_id="annihilation_party:modify",
    )
    async def modify(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction,
    ):
        event = await self.cog.event_for_interaction(interaction)
        if not event:
            return
        if _is_manager(interaction):
            if not any(party["members"] for party in event["parties"].values()):
                await interaction.response.send_message(
                    "There are no party entries to modify",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                "Choose the party containing the entry to modify",
                view=StaffPartyPickerView(
                    self.cog,
                    interaction.user.id,
                    event,
                    "modify",
                ),
                ephemeral=True,
            )
            return

        member = _member_for_discord_in_event(event, interaction.user.id)
        if not member:
            await interaction.response.send_message(
                "You didnt join any party yet, use **Join party** first",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            PartyEntryModal(
                self.cog,
                event,
                member=member,
                actor_can_manage=False,
            )
        )

    @discord.ui.button(
        label="Leave party",
        emoji="🚪",
        style=discord.ButtonStyle.danger,
        custom_id="annihilation_party:leave",
    )
    async def leave(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction,
    ):
        event = await self.cog.event_for_interaction(interaction)
        if not event:
            return
        member = _member_for_discord_in_event(event, interaction.user.id)
        if member:
            await interaction.response.send_message(
                content=f"Leave Party {member['party_number']}?",
                view=ConfirmRemovalView(
                    self.cog,
                    interaction.user.id,
                    event["id"],
                    member,
                    can_manage=False,
                ),
                ephemeral=True,
            )
            return

        if _is_manager(interaction):
            if not any(party["members"] for party in event["parties"].values()):
                await interaction.response.send_message(
                    "There are no party entries to remove",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                "Choose the party containing the entry to remove",
                view=StaffPartyPickerView(
                    self.cog,
                    interaction.user.id,
                    event,
                    "remove",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "You didnt join any party yet",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Change world",
        emoji="🌍",
        style=discord.ButtonStyle.secondary,
        custom_id="annihilation_party:world",
    )
    async def world(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction,
    ):
        event = await self.cog.event_for_interaction(interaction)
        if not event:
            return
        member = _member_for_discord_in_event(event, interaction.user.id)
        if member and member["is_leader"]:
            party = event["parties"][member["party_number"]]
            await interaction.response.send_modal(
                WorldModal(
                    self.cog,
                    event["id"],
                    member["party_number"],
                    party.get("world"),
                    can_manage=False,
                )
            )
            return

        if _is_manager(interaction):
            if not any(party["members"] for party in event["parties"].values()):
                await interaction.response.send_message(
                    "There are no parties with members yet",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                "Choose the party whose world should change",
                view=StaffPartyPickerView(
                    self.cog,
                    interaction.user.id,
                    event,
                    "world",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Only the current party leader can change the paryt world",
            ephemeral=True,
        )


class AnnihilationParties(commands.Cog):
    def __init__(self, client: discord.Bot):
        self.client = client
        self._event_locks: dict[int, asyncio.Lock] = {}
        self._creation_locks: dict[str, asyncio.Lock] = {}
        self._refresh_locks: dict[int, asyncio.Lock] = {}
        self._event_cache_by_id: dict[int, dict] = {}
        self._event_cache_by_message: dict[int, dict] = {}
        self._board_message_cache: dict[int, discord.Message] = {}
        self._persistent_view_registered = False
        self._close_boards.start()

    def cog_unload(self):
        if self._close_boards.is_running():
            self._close_boards.cancel()

    def _event_lock(self, event_id: int) -> asyncio.Lock:
        return self._event_locks.setdefault(event_id, asyncio.Lock())

    def _creation_lock(self, schedule_at: datetime.datetime) -> asyncio.Lock:
        return self._creation_locks.setdefault(schedule_at.isoformat(), asyncio.Lock())

    def _refresh_lock(self, event_id: int) -> asyncio.Lock:
        return self._refresh_locks.setdefault(event_id, asyncio.Lock())

    def _remember_board_message(self, message: discord.Message | None) -> None:
        message_id = getattr(message, "id", None)
        if message_id:
            self._board_message_cache[message_id] = message

    def _remember_event(self, event: dict | None) -> None:
        if not event:
            return

        event_id = event["id"]
        message_id = event.get("message_id")
        if event["status"] != "active":
            self._event_cache_by_id.pop(event_id, None)
            if message_id:
                self._event_cache_by_message.pop(message_id, None)
            return

        self._event_cache_by_id[event_id] = event
        if message_id:
            self._event_cache_by_message[message_id] = event

    def _forget_event(self, event_id: int) -> None:
        event = self._event_cache_by_id.pop(event_id, None)
        if event and event.get("message_id"):
            self._event_cache_by_message.pop(event["message_id"], None)

    def _schedule_board_refresh(self, event_id: int) -> None:
        task = asyncio.create_task(self._refresh_board_locked(event_id))
        task.add_done_callback(
            lambda done_task: self._log_refresh_failure(event_id, done_task)
        )

    async def _refresh_board_locked(self, event_id: int) -> None:
        async with self._refresh_lock(event_id):
            await self.refresh_board(event_id)

    def _log_refresh_failure(self, event_id: int, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            log(
                ERROR,
                f"Background refresh failed for Annihilation board {event_id}: {exc!r}",
                context="annihilation_parties",
            )

    def _cached_active_event_for_message(self, message_id: int) -> dict | None:
        event = self._event_cache_by_message.get(message_id)
        if not event:
            return None
        if event["status"] != "active" or event["closes_at"] <= utc_now():
            self._event_cache_by_message.pop(message_id, None)
            self._event_cache_by_id.pop(event["id"], None)
            return None
        return event

    def active_event_snapshot(self, event_id: int) -> dict | None:
        event = self._event_cache_by_id.get(event_id)
        if not event:
            return None
        if event["status"] != "active" or event["closes_at"] <= utc_now():
            self._event_cache_by_id.pop(event_id, None)
            if event.get("message_id"):
                self._event_cache_by_message.pop(event["message_id"], None)
            return None
        return event

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._persistent_view_registered:
            self.client.add_view(AnnihilationPartyView(self))
            self._persistent_view_registered = True

    def _embeds(self, event: dict) -> list[discord.Embed]:
        embeds = build_board_embeds(event)
        if BOARD_ICON_PATH.exists():
            embeds[0].set_thumbnail(url=f"attachment://{BOARD_ICON_FILENAME}")
        return embeds

    async def event_for_interaction(
        self,
        interaction: discord.Interaction,
    ) -> dict | None:
        message_id = getattr(interaction.message, "id", None)
        if not message_id:
            await interaction.response.send_message(
                "Could not identify this Annihilation party board.",
                ephemeral=True,
            )
            return None
        self._remember_board_message(interaction.message)
        cached_event = self._cached_active_event_for_message(message_id)
        if cached_event:
            return cached_event
        event = await asyncio.to_thread(get_event_by_message, message_id)
        if not event:
            await interaction.response.send_message(
                "This Annihilation party board is no longer registered.",
                ephemeral=True,
            )
            return None
        if event["status"] != "active" or event["closes_at"] <= utc_now():
            await interaction.response.send_message(
                "Sign-ups for this Annihilation event are closed",
                ephemeral=True,
            )
            return None
        self._remember_event(event)
        return event

    async def ensure_board(
        self,
        schedule_at: datetime.datetime,
        message: discord.Message | None = None,
    ) -> discord.Message | None:
        async with self._creation_lock(schedule_at):
            source_message = message
            if source_message is not None:
                channel = source_message.channel
            else:
                channel = self.client.get_channel(ANNIHILATION_ANNOUNCEMENT_CHANNEL_ID)
                if channel is None:
                    channel = await self.client.fetch_channel(
                        ANNIHILATION_ANNOUNCEMENT_CHANNEL_ID
                    )
            guild = getattr(channel, "guild", None)
            if guild is None:
                raise RuntimeError(
                    "The Annihilation announcement channel is not in a guild."
                )

            event = await asyncio.to_thread(
                ensure_event,
                schedule_at,
                guild.id,
                channel.id,
            )
            if event["status"] != "active":
                return None
            event = await asyncio.to_thread(get_event, event["id"])
            self._remember_event(event)

            board_message = None
            if event["message_id"]:
                try:
                    board_message = await channel.fetch_message(event["message_id"])
                    self._remember_board_message(board_message)
                except discord.NotFound:
                    board_message = None

            if board_message is None:
                if source_message is not None:
                    board_message = source_message
                else:
                    kwargs = {
                        "embeds": self._embeds(event),
                        "view": AnnihilationPartyView(self),
                        "allowed_mentions": discord.AllowedMentions.none(),
                    }
                    if BOARD_ICON_PATH.exists():
                        kwargs["file"] = discord.File(
                            str(BOARD_ICON_PATH),
                            filename=BOARD_ICON_FILENAME,
                        )
                    board_message = await channel.send(**kwargs)
                self._remember_board_message(board_message)
                await asyncio.to_thread(set_board_message, event["id"], board_message.id)
                event["message_id"] = board_message.id
                self._remember_event(event)

            if not event.get("thread_id"):
                try:
                    thread = await board_message.create_thread(
                        name=f"Annihilation • {event['schedule_at']:%Y-%m-%d}",
                        auto_archive_duration=1440,
                    )
                    await thread.send(
                        "Use the party board buttons on the parent message to join, "
                        "modify, or leave a party.\n\n"
                        f"Party board: {board_message.jump_url}",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    await asyncio.to_thread(set_board_thread, event["id"], thread.id)
                except discord.HTTPException as exc:
                    log(
                        WARN,
                        f"Could not create Annihilation discussion thread: {exc!r}",
                        context="annihilation_parties",
                    )

            await self.refresh_board(event["id"], message=board_message)
            return board_message

    async def refresh_board(
        self,
        event_id: int,
        *,
        message: discord.Message | None = None,
    ) -> None:
        event = await asyncio.to_thread(get_event, event_id)
        if not event or not event.get("message_id"):
            return
        self._remember_event(event)
        message_id = event["message_id"]
        if message is not None and getattr(message, "id", None) != message_id:
            message = None
        if message is None:
            message = self._board_message_cache.get(message_id)
        try:
            if message is None:
                channel = self.client.get_channel(event["channel_id"])
                if channel is None:
                    channel = await self.client.fetch_channel(event["channel_id"])
                message = await channel.fetch_message(message_id)
            self._remember_board_message(message)
            await message.edit(
                embeds=self._embeds(event),
                view=AnnihilationPartyView(self)
                if event["status"] == "active"
                else None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.NotFound:
            self._board_message_cache.pop(message_id, None)
            log(
                WARN,
                f"Annihilation board message {event['message_id']} was deleted",
                context="annihilation_parties",
            )

    async def submit_entry(
        self,
        interaction: discord.Interaction,
        *,
        event_id: int,
        member_id: int | None,
        actor_can_manage: bool,
        build: str,
        party_number: int,
        combat_role: str | None,
        bringing_scrolls: bool,
        notes: str | None,
    ) -> None:
        try:
            async with self._event_lock(event_id):
                if member_id is None:
                    linked = await asyncio.to_thread(
                        get_linked_account,
                        interaction.user.id,
                    )
                    if not linked:
                        raise AnnihilationPartyError(
                            "Account not linked"
                        )
                    await asyncio.to_thread(
                        add_member,
                        event_id,
                        interaction.user.id,
                        linked["ign"],
                        build,
                        party_number,
                        combat_role,
                        bringing_scrolls,
                        notes,
                    )
                    action = "joined"
                else:
                    await asyncio.to_thread(
                        update_member,
                        event_id,
                        interaction.user.id,
                        member_id,
                        actor_can_manage and _is_manager(interaction),
                        build,
                        party_number,
                        combat_role,
                        bringing_scrolls,
                        notes,
                    )
                    action = "updated"
        except AnnihilationPartyError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:
            log(
                ERROR,
                f"Failed to submit Annihilation party entry: {exc!r}",
                context="annihilation_parties",
            )
            await interaction.followup.send(
                "Could not save that party entry. Please try again",
                ephemeral=True,
            )
            return

        self._forget_event(event_id)
        self._schedule_board_refresh(event_id)
        if action == "joined":
            message = f"You joined party {party_number}"
        else:
            message = f"You updated your info in party {party_number}"
        await interaction.followup.send(message, ephemeral=True)

    async def remove_entry(
        self,
        interaction: discord.Interaction,
        *,
        event_id: int,
        member_id: int,
        can_manage: bool,
    ) -> None:
        try:
            async with self._event_lock(event_id):
                removed = await asyncio.to_thread(
                    remove_member,
                    event_id,
                    interaction.user.id,
                    member_id,
                    can_manage and _is_manager(interaction),
                )
        except AnnihilationPartyError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:
            log(
                ERROR,
                f"Failed to remove Annihilation party entry: {exc!r}",
                context="annihilation_parties",
            )
            await interaction.followup.send(
                "Could not remove that party entry. Please try again",
                ephemeral=True,
            )
            return

        self._forget_event(event_id)
        self._schedule_board_refresh(event_id)
        await interaction.followup.send(
            f"Removed **{removed['ign']}** from Party {removed['party_number']}",
            ephemeral=True,
        )

    async def change_world(
        self,
        interaction: discord.Interaction,
        *,
        event_id: int,
        party_number: int,
        world: str,
        can_manage: bool,
    ) -> None:
        try:
            async with self._event_lock(event_id):
                normalized_world = await asyncio.to_thread(
                    set_party_world,
                    event_id,
                    interaction.user.id,
                    party_number,
                    world,
                    can_manage and _is_manager(interaction),
                )
        except AnnihilationPartyError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:
            log(
                ERROR,
                f"Failed to change Annihilation party world: {exc!r}",
                context="annihilation_parties",
            )
            await interaction.followup.send(
                "Could not change that party world. Please try again",
                ephemeral=True,
            )
            return

        self._forget_event(event_id)
        self._schedule_board_refresh(event_id)
        await interaction.followup.send(
            f"Party {party_number} is now meeting on **{normalized_world}**",
            ephemeral=True,
        )

    async def _finalize_closed_board(self, event: dict) -> None:
        full_event = await asyncio.to_thread(get_event, event["id"])
        if not full_event:
            return
        channel = self.client.get_channel(full_event["channel_id"])
        if channel is None:
            channel = await self.client.fetch_channel(full_event["channel_id"])

        if full_event.get("message_id"):
            message_id = full_event["message_id"]
            try:
                message = self._board_message_cache.get(message_id)
                if message is None:
                    message = await channel.fetch_message(message_id)
                self._remember_board_message(message)
                await message.edit(
                    embeds=self._embeds(full_event),
                    view=None,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.NotFound:
                self._board_message_cache.pop(message_id, None)

        if full_event.get("thread_id"):
            thread = self.client.get_channel(full_event["thread_id"])
            if thread is None:
                try:
                    thread = await self.client.fetch_channel(full_event["thread_id"])
                except discord.NotFound:
                    thread = None
            if thread is not None:
                try:
                    if not getattr(thread, "archived", False):
                        await thread.send(
                            "Annihilation sign-ups are now closed. Threat is being archived",
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    await thread.edit(
                        locked=True,
                        archived=True,
                        reason="Annihilation sign-ups closed",
                    )
                except discord.HTTPException as exc:
                    log(
                        WARN,
                        f"Could not archive Annihilation thread {thread.id}: {exc!r}",
                        context="annihilation_parties",
                    )
                    raise

        await asyncio.to_thread(mark_discord_closed, full_event["id"])
        log(
            SUCCESS,
            f"Closed Annihilation party board for {full_event['schedule_at'].isoformat()}",
            context="annihilation_parties",
        )

    @tasks.loop(minutes=1)
    async def _close_boards(self):
        try:
            await asyncio.to_thread(close_due_events)
            events = await asyncio.to_thread(get_unfinalized_closed_events)
            for event in events:
                try:
                    async with self._event_lock(event["id"]):
                        await self._finalize_closed_board(event)
                except Exception as exc:
                    log(
                        ERROR,
                        f"Failed to finalize Annihilation board {event['id']}: {exc!r}",
                        context="annihilation_parties",
                    )
        except Exception as exc:
            log(
                ERROR,
                f"Annihilation board close loop failed: {exc!r}",
                context="annihilation_parties",
            )

    @_close_boards.before_loop
    async def _wait_until_ready(self):
        await self.client.wait_until_ready()

    @discord.slash_command(
        name="annihilation-party-test",
        description="TEST: Create fake anni partyboard",
        default_member_permissions=discord.Permissions(administrator=True),
        guild_ids=HOME_GUILD_IDS,
    )
    async def annihilation_party_test(
        self,
        ctx: discord.ApplicationContext,
        starts_in_minutes: discord.Option(
            int,
            "Fake Annihilation start offset",
            required=False,
            default=60,
            min_value=0,
            max_value=10080,
        ),
    ):
        await ctx.defer(ephemeral=True)

        schedule_at = datetime.datetime.now(
            datetime.timezone.utc
        ) + datetime.timedelta(minutes=starts_in_minutes)
        schedule_at = schedule_at.replace(microsecond=0)
        message = await self.ensure_board(schedule_at)
        if message is None:
            await ctx.followup.send(
                "Could not create a test Annihilation party board.",
                ephemeral=True,
            )
            return

        await ctx.followup.send(
            "Created test Annihilation party board: "
            f"{message.jump_url}\n"
            f"Fake start: <t:{int(schedule_at.timestamp())}:F>",
            ephemeral=True,
        )


def setup(client):
    client.add_cog(AnnihilationParties(client))
