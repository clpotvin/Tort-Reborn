import discord
import requests
from discord.ext import commands
from discord.commands import SlashCommandGroup
from datetime import datetime

class LootPool(commands.Cog):
    lootpool = SlashCommandGroup(
        name="lootpool",
        description="Commands to fetch weekly lootpool data"
    )

    def __init__(self, client):
        self.client = client

    def _format_list(self, items):
        return "\n".join(items) if items else "None"

    async def _init_session(self):
        session = requests.Session()
        try:
            session.get("https://nori.fish/api/tokens")
        except Exception:
            pass
        return session

    @lootpool.command(
        name="aspects",
        description="Provides weekly aspects data"
    )
    async def aspects(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        try:
            resp = requests.get("https://nori.fish/api/aspects")
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            embed = discord.Embed(
                title=":no_entry: Error",
                description="Failed to fetch aspects data. Please try again later.",
                color=0xe33232
            )
            await ctx.followup.send(embed=embed)
            return

        timestamp = data.get("Timestamp")
        embed = discord.Embed(
            title="Weekly Aspects Lootpool",
            color=0x4585db,
            timestamp=datetime.utcfromtimestamp(timestamp)
        )
        loot = data.get("Loot", {})
        count = 0
        for raid_name, rarities in loot.items():
            if count and count % 2 == 0:
                embed.add_field(name='\u200b', value='\u200b', inline=False)
            mythic = self._format_list(rarities.get("Mythic", []))
            fabled = self._format_list(rarities.get("Fabled", []))
            legendary = self._format_list(rarities.get("Legendary", []))
            value = (
                f"**Mythic**:\n{mythic}\n"
                f"**Fabled**:\n{fabled}\n"
                f"**Legendary**:\n{legendary}"
            )
            embed.add_field(name=raid_name, value=value, inline=True)
            count += 1

        embed.set_footer(text=f"Last Updated: {datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        await ctx.followup.send(embed=embed)

    @lootpool.command(
        name="lootruns",
        description="Provides weekly loot run data (Mythic Only)"
    )
    async def lootruns(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        session = await self._init_session()
        csrf_token = session.cookies.get('csrf_token') or session.cookies.get('csrftoken')
        headers = {}
        if csrf_token:
            headers['X-CSRF-Token'] = csrf_token

        try:
            resp = session.get("https://nori.fish/api/lootpool", headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            embed = discord.Embed(
                title=":no_entry: Error",
                description="Failed to fetch loot run data. Please try again later.",
                color=0xe33232
            )
            await ctx.followup.send(embed=embed)
            return

        timestamp = data.get("Timestamp")
        embed = discord.Embed(
            title="Weekly Loot Runs (Mythic Only)",
            color=0x4585db,
            timestamp=datetime.utcfromtimestamp(timestamp)
        )
        loot = data.get("Loot", {})
        for region, region_data in loot.items():
            shiny_info = region_data.get("Shiny", {})
            shiny_item = shiny_info.get("Item")
            tracker = shiny_info.get("Tracker")
            mythics = region_data.get("Mythic", [])
            mythics_filtered = [m for m in mythics if m != shiny_item]
            lines = []
            if shiny_item:
                lines.append(f"**Shiny**: {shiny_item} ⭐\n(Tracker: {tracker})")
            if mythics_filtered:
                lines.append("**Mythics**:")
                lines.extend(mythics_filtered)
            else:
                lines.append("**Mythics**: None")
            value = "\n".join(lines)
            embed.add_field(name=region, value=value, inline=True)

        embed.set_footer(text=f"Last Updated: {datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        await ctx.followup.send(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self):
        print("LootPool cog loaded")


def setup(client):
    client.add_cog(LootPool(client))
