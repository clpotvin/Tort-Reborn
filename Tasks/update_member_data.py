import asyncio
import json
import os
import discord
from discord.ext import tasks, commands
from Helpers.classes import Guild
from Helpers.functions import getPlayerDatav3

RAID_ANNOUNCE_CHANNEL_ID = 1370124586036887652


class UpdateMemberData(commands.Cog):
    RAID_NAMES = [
        "Nest of the Grootslangs",
        "The Canyon Colossus",
        "The Nameless Anomaly",
        "Orphion's Nexus of Light"
    ]

    def __init__(self, client):
        self.client = client

        self.previous_raid_data = self._load_json("previous_raid_data.json", {})

        self.raid_participants = {raid: [] for raid in self.RAID_NAMES}

        self.cold_start = True

        # self.test = 0

    def _load_json(self, path, default):
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return default

    def _save_json(self, path, data):
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _make_progress_bar(self, percent: int, length: int = 20) -> str:
        """Return a simple text bar, e.g. [██████────────────]."""
        filled = int(length * percent / 100)
        bar = "█" * filled + "─" * (length - filled)
        return f"[{bar}]"

    @tasks.loop(minutes=0.5)
    async def update_member_data(self):
        guild = Guild("The Aquarium")
        await self.client.change_presence(
            activity=discord.CustomActivity(name=f"{guild.online} members online")
        )

        new_raid_data = {}
        snapshot = []

        for i, member in enumerate(guild.all_members):
            # only test first 8
            # if i > 8:
            #     break

            m = getPlayerDatav3(member["uuid"])
            uuid = m["uuid"]
            name = m["username"]
            raids = m.get("globalData", {}).get("raids", {}).get("list", {})

            new_raid_data[uuid] = {
                raid: raids.get(raid, 0) for raid in self.RAID_NAMES
            }

            # test increments
            # if self.test == 1 and i < 4:
            #     new_raid_data[uuid]["Nest of the Grootslangs"] += 1
            # if self.test == 1 and 4 <= i < 8:
            #     new_raid_data[uuid]["The Nameless Anomaly"] += 1

            snapshot.append({
                "name":        name,
                "uuid":        uuid,
                "rank":        member["rank"],
                "playtime":    m["playtime"],
                "last_join":   m["lastJoin"],
                "contributed": member["contributed"],
                "wars":        m.get("globalData", {}).get("wars", 0),
                "raids":       new_raid_data[uuid],
            })

            if not self.cold_start:
                old = self.previous_raid_data.get(uuid, {})
                for raid in self.RAID_NAMES:
                    if new_raid_data[uuid][raid] > old.get(raid, 0):
                        if name not in self.raid_participants[raid]:
                            self.raid_participants[raid].append(name)

                            if len(self.raid_participants[raid]) == 4:
                                print(
                                    f"[GUILD RAID] {raid} completed by: "
                                    f"{', '.join(self.raid_participants[raid])}"
                                )

                                channel = self.client.get_channel(RAID_ANNOUNCE_CHANNEL_ID)
                                if channel:
                                    current_xp = guild.xpPercent
                                    bar = self._make_progress_bar(current_xp)
                                    embed = discord.Embed(
                                        title="🏹 Guild Raid Completed!",
                                        description=(
                                            f"**{raid}** completed by: "
                                            f"{', '.join(self.raid_participants[raid])}"
                                        ),
                                        color=discord.Color.blue()
                                    )
                                    embed.set_footer(
                                        text=(
                                            f"Lv.{guild.level} – THE AQUARIUM – "
                                            f"{current_xp}% XP  {bar}"
                                        )
                                    )
                                    await channel.send(embed=embed)

                                self.raid_participants[raid] = []

            # print(name)
            await asyncio.sleep(0.5)

        self.previous_raid_data = new_raid_data
        self._save_json("previous_raid_data.json", new_raid_data)

        self.cold_start = False

        with open("current_activity.json", "w") as f:
            json.dump(snapshot, f, indent=2)

        # self.test += 1

    @update_member_data.before_loop
    async def before_update(self):
        await self.client.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        print("UpdateMemberData task loaded")
        self.update_member_data.start()


def setup(client):
    client.add_cog(UpdateMemberData(client))
