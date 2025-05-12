import asyncio
import json
import os
import discord
from discord.ext import tasks, commands

from Helpers.classes import Guild, DB
from Helpers.functions import getPlayerDatav3
from Helpers.variables import raid_log_channel

RAID_ANNOUNCE_CHANNEL_ID = raid_log_channel

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

        self.update_member_data.start()

    def _load_json(self, path, default):
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[UpdateMemberData] Failed to load {path}: {e}")
        return default

    def _save_json(self, path, data):
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[UpdateMemberData] Failed to save {path}: {e}")

    def _make_progress_bar(self, percent: int, length: int = 20) -> str:
        filled = int(length * percent / 100)
        bar = "█" * filled + "─" * (length - filled)
        return f"[{bar}]"

    @tasks.loop(minutes=5)
    async def update_member_data(self):
        db = None
        try:
            db = DB()
            db.connect()

            guild = Guild("The Aquarium")
            await self.client.change_presence(
                activity=discord.CustomActivity(name=f"{guild.online} members online")
            )

            new_raid_data = {}
            snapshot = []

            for member in guild.all_members:
                try:
                    m = getPlayerDatav3(member["uuid"])
                    if not isinstance(m, dict):
                        print(f"[UpdateMemberData] getPlayerDatav3 returned non-dict for {member['uuid']}: {m}")
                        continue

                    uuid = m.get("uuid")
                    name = m.get("username")
                    if not uuid or not name:
                        print(f"[UpdateMemberData] Missing uuid/name for member data: {m}")
                        continue

                    raids = m.get("globalData", {}).get("raids", {}).get("list", {})
                    new_raid_data[uuid] = {raid: raids.get(raid, 0) for raid in self.RAID_NAMES}

                    snapshot.append({
                        "name": name,
                        "uuid": uuid,
                        "rank": member.get("rank"),
                        "playtime": m.get("playtime"),
                        "last_join": m.get("lastJoin"),
                        "contributed": member.get("contributed"),
                        "wars": m.get("globalData", {}).get("wars", 0),
                        "raids": new_raid_data[uuid],
                    })

                    if not self.cold_start:
                        old = self.previous_raid_data.get(uuid, {})
                        for raid in self.RAID_NAMES:
                            new_count = new_raid_data[uuid][raid]
                            old_count = old.get(raid, 0)
                            if new_count > old_count:
                                if not any(p["uuid"] == uuid for p in self.raid_participants[raid]):
                                    self.raid_participants[raid].append({"uuid": uuid, "name": name})
                                    print(f"User {name} had {old_count} and now has {new_count}")
                                    if len(self.raid_participants[raid]) == 4:
                                        participants = self.raid_participants[raid]
                                        names = [p["name"] for p in participants]
                                        print(f"[GUILD RAID] {raid} completed by: {', '.join(names)}")

                                        channel = self.client.get_channel(RAID_ANNOUNCE_CHANNEL_ID)
                                        if channel:
                                            current_xp = guild.xpPercent
                                            bar = self._make_progress_bar(current_xp)
                                            embed = discord.Embed(
                                                title="🏹 Guild Raid Completed!",
                                                description=(
                                                    f"**{raid}** completed by: {', '.join(names)}"
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

                                        for p in participants:
                                            db.cursor.execute(
                                                """
                                                INSERT INTO uncollected_raids AS ur (uuid, uncollected_raids, collected_raids)
                                                VALUES (%s, 1, 0)
                                                ON CONFLICT (uuid)
                                                DO UPDATE SET
                                                  uncollected_raids = ur.uncollected_raids + EXCLUDED.uncollected_raids,
                                                  collected_raids   = ur.collected_raids   + EXCLUDED.collected_raids
                                                """,
                                                (p["uuid"],)
                                            )
                                        db.connection.commit()
                                        self.raid_participants[raid] = []
                except Exception as e:
                    print(f"[UpdateMemberData] Error processing {member.get('uuid')}: {e}")
                finally:
                    await asyncio.sleep(0.5)

            self.previous_raid_data = new_raid_data
            self._save_json("previous_raid_data.json", new_raid_data)
            with open("current_activity.json", "w") as f:
                json.dump(snapshot, f, indent=2)

            self.cold_start = False
        except Exception as e:
            print(f"[UpdateMemberData] Fatal error in update_member_data loop: {e}")
        finally:
            if db:
                try:
                    db.close()
                except:
                    pass

    @update_member_data.before_loop
    async def before_update(self):
        await self.client.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        print("UpdateMemberData task loaded")


def setup(client):
    client.add_cog(UpdateMemberData(client))
