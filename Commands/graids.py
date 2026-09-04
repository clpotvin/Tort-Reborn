from typing import Tuple

import discord
from discord.ext import commands
from discord.commands import slash_command, Option

from Helpers.raid_card import RaidCardBase
from Helpers.rate_limiter import external_rate_limit


class GuildRaids(RaidCardBase, commands.Cog):
    TITLE = "Guild Raids"
    FILE_PREFIX = "graids"
    STAT_KEY = "guildRaids"
    RANK_QUALIFIERS: Tuple[str, ...] = ("srgplayers",)

    RAIDS = [
        ("NOTG", "Nest of the Grootslangs", ("Nest of the Grootslangs",), ("grootslangSrGPlayers",), ("grootslang",)),
        ("NOL",  "Orphion's Nexus of Light", ("Orphion's Nexus of Light",), ("orphionSrGPlayers",), ("orphion",)),
        ("TCC",  "The Canyon Colossus", ("The Canyon Colossus",), ("colossusSrGPlayers",), ("colossus",)),
        ("TNA",  "The Nameless Anomaly", ("The Nameless Anomaly",), ("namelessSrGPlayers",), ("nameless", "anomaly")),
        # WTP is internally called "Fruma" by the API -- frumaSrGPlayers tracks WTP guild raid rank
        ("WTP",  "The Queen's Wartorn Palace", ("The Wartorn Palace", "Wartorn Palace"), ("frumaSrGPlayers",), ("fruma",)),
    ]

    @slash_command(
        name="graids",
        description="Show all-time guild raid rankings and counts for a player",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install},
        contexts={discord.InteractionContextType.guild, discord.InteractionContextType.bot_dm, discord.InteractionContextType.private_channel},
    )
    @external_rate_limit()
    async def graids(self,
                     ctx: discord.ApplicationContext,
                     name: Option(str, "Minecraft username", required=True)):
        await self._run(ctx, name)


def setup(client: commands.Bot):
    client.add_cog(GuildRaids(client))
