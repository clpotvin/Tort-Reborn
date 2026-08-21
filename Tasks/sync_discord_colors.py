import asyncio

from discord.ext import tasks, commands

from Helpers.logger import log, INFO, WARN, ERROR
from Helpers.discord_colors import (
    NO_COLORS,
    rank_role_colors,
    rendered_colors,
    stored_colors,
    stored_rank_colors,
    write_member_colors,
    write_rank_colors,
)
from Helpers.variables import TAQ_GUILD_ID


class SyncDiscordColors(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.sync_discord_colors.start()

    def cog_unload(self):
        self.sync_discord_colors.cancel()

    @tasks.loop(minutes=15)
    async def sync_discord_colors(self):
        if not self.client.is_ready():
            return

        guild = self.client.get_guild(TAQ_GUILD_ID)
        if guild is None:
            log(WARN, "TAq guild not in cache", context="sync_discord_colors")
            return

        # Ranks first: roles need no member cache, so a recolour still lands
        # on a run where the chunking below fails.
        await self._sync_ranks(guild)
        await self._sync_members(guild)

    async def _sync_ranks(self, guild):
        try:
            current = rank_role_colors(guild)
            stored = await asyncio.to_thread(stored_rank_colors)
        except Exception as e:
            log(ERROR, f"Failed to read rank colours: {e}", context="sync_discord_colors")
            return

        changed = {key: colors for key, colors in current.items() if stored.get(key) != colors}
        if not changed:
            return

        try:
            await asyncio.to_thread(write_rank_colors, changed)
        except Exception as e:
            log(ERROR, f"Failed to write rank colours: {e}", context="sync_discord_colors")
            return

        log(INFO, f"Updated {len(changed)} rank colours: {', '.join(sorted(changed))}",
            context="sync_discord_colors")

    async def _sync_members(self, guild):
        # A partial cache reads uncached members as gone and wipes their colours.
        if not guild.chunked:
            try:
                await guild.chunk()
            except Exception as e:
                log(ERROR, f"Failed to chunk guild members: {e}", context="sync_discord_colors")
                return

        try:
            stored = await asyncio.to_thread(stored_colors)
        except Exception as e:
            log(ERROR, f"Failed to read stored colours: {e}", context="sync_discord_colors")
            return

        updates = []
        for discord_id, previous in stored.items():
            member = guild.get_member(discord_id)
            current = rendered_colors(member) if member else NO_COLORS
            if current != previous:
                updates.append((discord_id, current))

        if not updates:
            return

        try:
            written = await asyncio.to_thread(write_member_colors, updates)
        except Exception as e:
            log(ERROR, f"Failed to write colours: {e}", context="sync_discord_colors")
            return

        log(INFO, f"Updated colours for {written}/{len(stored)} guild members",
            context="sync_discord_colors")

    @sync_discord_colors.before_loop
    async def before_sync(self):
        await self.client.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.sync_discord_colors.is_running():
            self.sync_discord_colors.start()


def setup(client):
    client.add_cog(SyncDiscordColors(client))
