import asyncio

import discord
from discord.ext import commands

from Helpers.database import DB
from Helpers.logger import log, ERROR
from Helpers.discord_colors import rendered_colors, write_member_colors
from Helpers.variables import ERROR_CHANNEL_ID, TAQ_GUILD_ID, is_home_guild


def _db_lookup_uuid(discord_id: int):
    """Blocking DB: look up UUID by Discord ID."""
    db = DB()
    try:
        db.connect()
        db.cursor.execute(
            "SELECT uuid FROM discord_links WHERE discord_id = %s",
            (discord_id,)
        )
        row = db.cursor.fetchone()
        return row[0] if row else None
    finally:
        db.close()


class OnMemberUpdate(commands.Cog):
    def __init__(self, client):
        self.client = client

    async def _sync_colors(self, before: discord.Member, after: discord.Member):
        # Ahead of the promotion checks below, which only see additions:
        # losing a coloured role changes the rendered colour too.
        if after.guild.id != TAQ_GUILD_ID:
            return

        colors = rendered_colors(after)
        if colors == rendered_colors(before):
            return

        try:
            await asyncio.to_thread(write_member_colors, [(after.id, colors)])
        except Exception as e:
            log(ERROR, f"Failed to store colours for {after.id}: {e}", context="on_member_update")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Ignore member updates from external (non-home) guilds
        if not is_home_guild(after.guild.id):
            return

        # Only care about role changes
        if before.roles == after.roles:
            return

        await self._sync_colors(before, after)

        added_roles = set(after.roles) - set(before.roles)
        if not added_roles:
            return

        added_names = {r.name for r in added_roles}
        if "Piranha" not in added_names:
            return

        try:
            # Look up UUID from discord_links (blocking, run in thread)
            uuid = await asyncio.to_thread(_db_lookup_uuid, after.id)
            if not uuid:
                return

            from Helpers.functions import getUsernameFromUUID
            ign = await asyncio.to_thread(getUsernameFromUUID, uuid)
            if not ign:
                return

            from Helpers.recruiting import credit_piranha_promotion
            await credit_piranha_promotion(self.client, ign)

        except Exception as e:
            err_ch = self.client.get_channel(ERROR_CHANNEL_ID)
            if err_ch:
                await err_ch.send(
                    f"## Recruiter Tracker - Role Promo Fallback Error\n"
                    f"**User:** <@{after.id}> | **Promo:** `piranhaPromo`\n"
                    f"```\n{str(e)[:500]}\n```"
                )


def setup(client):
    client.add_cog(OnMemberUpdate(client))
