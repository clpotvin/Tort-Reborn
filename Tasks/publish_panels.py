import asyncio
import json

import discord
from discord.ext import tasks, commands

from Helpers.logger import log, ERROR
from Helpers.panel_db import (
    claim_panels, mark_published, mark_error, delete_panel_row,
)
from Helpers.panel_render import build_embeds


def _as_list(published):
    # psycopg2 returns jsonb as already-parsed Python objects; guard for str just in case.
    if isinstance(published, str):
        return json.loads(published)
    return published or []


class PublishPanels(commands.Cog):
    def __init__(self, client):
        self.client = client

    @tasks.loop(minutes=1)
    async def publish_panels(self):
        publishes = await asyncio.to_thread(claim_panels, "publish")
        for panel_id, name, channel_id, message_id, published in publishes:
            try:
                await self._publish_one(panel_id, channel_id, message_id, published)
            except Exception as e:
                log(ERROR, f"Publish failed for panel {panel_id} ({name}): {e}",
                    context="publish_panels")
                await asyncio.to_thread(mark_error, panel_id, str(e))

        deletes = await asyncio.to_thread(claim_panels, "delete")
        for panel_id, name, channel_id, message_id, _published in deletes:
            try:
                await self._delete_one(channel_id, message_id)
            except Exception as e:
                log(ERROR, f"Delete failed for panel {panel_id} ({name}): {e}",
                    context="publish_panels")
            # Always drop the row: a delete request means the exec removed the panel.
            await asyncio.to_thread(delete_panel_row, panel_id)

    async def _publish_one(self, panel_id, channel_id, message_id, published):
        channel = self.client.get_channel(int(channel_id)) if channel_id else None
        if channel is None:
            raise RuntimeError("Target channel not found or bot lacks access")

        embeds, files = build_embeds(_as_list(published))
        if not embeds:
            raise RuntimeError("Panel has no embeds to publish")

        new_message_id = message_id
        if message_id:
            try:
                msg = await channel.fetch_message(int(message_id))
                # Editing cannot change attachments cleanly; re-send when the panel uses files.
                if files:
                    await msg.delete()
                    sent = await channel.send(embeds=embeds, files=files)
                    new_message_id = sent.id
                else:
                    await msg.edit(embeds=embeds, attachments=[])
            except discord.NotFound:
                sent = await channel.send(embeds=embeds, files=files)
                new_message_id = sent.id
        else:
            sent = await channel.send(embeds=embeds, files=files)
            new_message_id = sent.id

        await asyncio.to_thread(mark_published, panel_id, new_message_id)

    async def _delete_one(self, channel_id, message_id):
        if not (channel_id and message_id):
            return
        channel = self.client.get_channel(int(channel_id))
        if channel is None:
            return
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.delete()
        except discord.NotFound:
            return

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.publish_panels.is_running():
            self.publish_panels.start()


def setup(client):
    client.add_cog(PublishPanels(client))
