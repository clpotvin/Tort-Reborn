from typing import Tuple

import discord
from discord.ext import commands
from discord.commands import slash_command, Option

from Helpers.raid_card import RaidCardBase
from Helpers.rate_limiter import external_rate_limit


class Raids(RaidCardBase, commands.Cog):
    TITLE = "Raids"
    COUNT_LABEL = "Clears"
    FILE_PREFIX = "raids"
    STAT_KEY = "raids"
    RANK_QUALIFIERS: Tuple[str, ...] = ("completion", "srplayers")

    RAIDS = [
        ("NOTG", "Nest of the Grootslangs", ("Nest of the Grootslangs",), ("grootslangCompletion",), ("grootslang",)),
        ("NOL",  "Orphion's Nexus of Light", ("Orphion's Nexus of Light",), ("orphionCompletion",), ("orphion",)),
        ("TCC",  "The Canyon Colossus", ("The Canyon Colossus",), ("colossusCompletion",), ("colossus",)),
        ("TNA",  "The Nameless Anomaly", ("The Nameless Anomaly",), ("namelessCompletion",), ("nameless", "anomaly")),
        # WTP is internally called "Fruma" by the API -- frumaCompletion tracks WTP clears
        ("WTP",  "The Queen's Wartorn Palace", ("The Wartorn Palace", "Wartorn Palace"), ("frumaCompletion",), ("fruma",)),
    ]

    @slash_command(
        name="raids",
        description="Show raid rankings and counts for a player",
        integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install},
        contexts={discord.InteractionContextType.guild, discord.InteractionContextType.bot_dm, discord.InteractionContextType.private_channel},
    )
    @external_rate_limit()
    async def raids(self,
                    ctx: discord.ApplicationContext,
                    name: Option(str, "Minecraft username", required=True)):
        await self._run(ctx, name)


def setup(client: commands.Bot):
    client.add_cog(Raids(client))
