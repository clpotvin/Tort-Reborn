import asyncio
import json
import discord

from discord.ext import tasks, commands

from Helpers.classes import Guild
from Helpers.functions import getPlayerDatav3


class UpdateMemberData(commands.Cog):
    def __init__(self, client):
        self.client = client

    @tasks.loop(minutes=15)
    async def update_member_data(self):
        guild = Guild('The Aquarium')
        taq = guild.all_members
        await self.client.change_presence(activity=discord.CustomActivity(name=f'{guild.online} members online'))
        memberlist = []
        for member in taq:
            mber = getPlayerDatav3(member['uuid'])
            memberlist.append(
                {"name": mber['username'], "uuid": mber['uuid'], "rank": member['rank'],
                 "playtime": mber['playtime'], "last_join": mber['lastJoin'],
                 "contributed": member['contributed'], 'wars': mber['globalData']['wars']})
            await asyncio.sleep(.5)
        with open("current_activity.json", 'w') as f:
            json.dump(memberlist, f)

    @update_member_data.before_loop
    async def update_member_data_before_loop(self):
        await self.client.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        print('UpdateMemberData task loaded')
        self.update_member_data.start()


def setup(client):
    client.add_cog(UpdateMemberData(client))
