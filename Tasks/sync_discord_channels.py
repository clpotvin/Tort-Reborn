import asyncio

import discord
from discord.ext import tasks, commands

from Helpers.logger import log, ERROR
from Helpers.variables import TAQ_GUILD_ID
from Helpers.panel_db import ensure_panel_tables, upsert_channels, prune_channels


class SyncDiscordChannels(commands.Cog):
    def __init__(self, client):
        self.client = client

    @tasks.loop(minutes=5)
    async def sync_channels(self):
        guild = self.client.get_guild(TAQ_GUILD_ID)
        if not guild:
            return
        rows = []
        keep = []
        for ch in guild.text_channels:
            category = ch.category.name if ch.category else None
            rows.append((ch.id, ch.name, category, ch.position))
            keep.append(ch.id)
        try:
            await asyncio.to_thread(upsert_channels, rows)
            await asyncio.to_thread(prune_channels, keep)
        except Exception as e:
            log(ERROR, f"Channel sync failed: {e}", context="sync_discord_channels")

    @commands.Cog.listener()
    async def on_ready(self):
        await asyncio.to_thread(ensure_panel_tables)
        if not self.sync_channels.is_running():
            self.sync_channels.start()


def setup(client):
    client.add_cog(SyncDiscordChannels(client))
