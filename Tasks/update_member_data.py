import asyncio
import json
import os
import discord
import datetime
from datetime import timezone, timedelta
from discord.ext import tasks, commands

from Helpers.classes import Guild, DB
from Helpers.functions import getPlayerDatav3
from Helpers.variables import raid_log_channel, notg_emoji_id, tcc_emoji_id, tna_emoji_id, nol_emoji_id

RAID_ANNOUNCE_CHANNEL_ID = raid_log_channel
GUILD_TTL = timedelta(minutes=10)
XP_THRESHOLD = 10_000_000

RAID_EMOJIS = {
    "Nest of the Grootslangs": notg_emoji_id,
    "The Canyon Colossus": tcc_emoji_id,
    "The Nameless Anomaly": tna_emoji_id,
    "Orphion's Nexus of Light": nol_emoji_id
}

class UpdateMemberData(commands.Cog):
    RAID_NAMES = [
        "Nest of the Grootslangs",
        "The Canyon Colossus",
        "The Nameless Anomaly",
        "Orphion's Nexus of Light"
    ]

    def __init__(self, client):
        self.client = client
        self.previous_data = self._load_json("previous_data.json", {})
        # track users: raid_name -> { uuid: {"name": str, "first_seen": datetime} }
        self.raid_participants = {raid: {} for raid in self.RAID_NAMES}
        self.pending_verification = {raid: {} for raid in self.RAID_NAMES}
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

    async def _announce_raid(self, raid, group, guild, db):
        names = [self.raid_participants[raid][uid]["name"] for uid in group]
        bolded = [f"**{n}**" for n in names]
        if len(bolded) > 1:
            *first, last = bolded
            names_str = ", ".join(first) + ", and " + last
        else:
            names_str = bolded[0]

        emoji = RAID_EMOJIS.get(raid, "")
        message = f"{names_str} completed\n{emoji} **{raid}** guild raid!"

        now = datetime.datetime.now(timezone.utc)
        print(f"{now} - ANNOUNCE: {message}")

        channel = self.client.get_channel(RAID_ANNOUNCE_CHANNEL_ID)
        if channel:
            await channel.send(message)

        for uid in group:
            db.cursor.execute(
                """
                INSERT INTO uncollected_raids (uuid, uncollected_raids, collected_raids)
                VALUES (%s, 1, 0)
                ON CONFLICT (uuid) DO UPDATE
                  SET uncollected_raids = uncollected_raids + 1
                """,
                (uid,)
            )
        db.connection.commit()

    @tasks.loop(minutes=5)
    async def update_member_data(self):
        now = datetime.datetime.now(timezone.utc)
        if self.cold_start:
            print(f"{now} - Starting member tracking (cold start)")

        cutoff = now - GUILD_TTL
        for raid, parts in self.raid_participants.items():
            for uid, info in list(parts.items()):
                raw = info["first_seen"] if isinstance(info, dict) else info
                if isinstance(raw, str):
                    try:
                        first_seen = datetime.datetime.fromisoformat(raw)
                    except ValueError:
                        first_seen = datetime.datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                else:
                    first_seen = raw
                if first_seen < cutoff:
                    name = info["name"] if isinstance(info, dict) else str(uid)
                    print(f"{now} - PRUNE: {name} ({uid}) from {raid} (seen {first_seen})")
                    parts.pop(uid, None)

        db = None
        try:
            db = DB(); db.connect()
            guild = Guild("The Aquarium")
            await self.client.change_presence(
                activity=discord.CustomActivity(name=f"{guild.online} members online")
            )

            new_data = {}
            for member in guild.all_members:
                m = getPlayerDatav3(member["uuid"])
                if not isinstance(m, dict):
                    continue

                uuid = m.get("uuid")
                name = m.get("username")
                if not uuid or not name:
                    continue

                contributed = member.get("contributed", 0)
                raids = m.get("globalData", {}).get("raids", {}).get("list", {})
                new_data[uuid] = {
                    "contributed": contributed,
                    "raids": {r: raids.get(r, 0) for r in self.RAID_NAMES}
                }

                if not self.cold_start:
                    old = self.previous_data.get(uuid, {"contributed": 0, "raids": {}})
                    for raid in self.RAID_NAMES:
                        new_count = new_data[uuid]["raids"][raid]
                        old_count = old["raids"].get(raid, 0)
                        diff = new_count - old_count
                        if 0 < diff < 3:
                            parts = self.raid_participants[raid]
                            if uuid not in parts and len(parts) < 4:
                                parts[uuid] = {"name": name, "first_seen": now}
                                print(f"{now} - DETECT: {name} in {raid}, count {old_count}->{new_count}")
                            if len(parts) == 4:
                                group = frozenset(parts.keys())
                                if group not in self.pending_verification[raid]:
                                    self.pending_verification[raid][group] = now
                                    print(f"{now} - SCHEDULE VERIFICATION for group {group} on {raid}")

                await asyncio.sleep(0.5)

            for raid, pend in self.pending_verification.items():
                for group, detect_time in list(pend.items()):
                    if now - detect_time >= GUILD_TTL:
                        print(f"{now} - VERIFY: group {group} for {raid}")
                        passed = all(
                            new_data[uid]["contributed"] -
                            self.previous_data.get(uid, {"contributed": 0})["contributed"]
                            >= XP_THRESHOLD
                            for uid in group
                        )
                        if passed:
                            print(f"{now} - VERIFICATION PASSED for group {group} on {raid}")
                            await self._announce_raid(raid, group, guild, db)
                        else:
                            print(f"{now} - VERIFICATION FAILED for group {group} on {raid}")
                        for uid in group:
                            self.raid_participants[raid].pop(uid, None)
                        del pend[group]

            self.previous_data = new_data
            self._save_json("previous_data.json", new_data)
            if self.cold_start:
                print(f"{now} - Ending cold start")
                self.cold_start = False

        except Exception as e:
            print(f"{now} - [UpdateMemberData] Fatal error: {e}")
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
        print(f"{datetime.datetime.now(timezone.utc)} - UpdateMemberData task loaded")


def setup(client):
    client.add_cog(UpdateMemberData(client))
