import json
import os
import sys
import time

from discord.ext import commands
from discord import slash_command


class Restart(commands.Cog):
    def __init__(self, client):
        self.client = client

    @slash_command(guild_ids=[1053447772302479421])
    async def restart(self, message):
        crash = {"type": 'Restart', "value": str(message.user) + ' ran the restart command', "timestamp": int(time.time())}
        with open('last_online.json', 'w') as f:
            json.dump(crash, f)
        await message.respond('Restarting...', ephemeral=True)
        os.execv(sys.executable, ['python'] + sys.argv)

    @commands.Cog.listener()
    async def on_ready(self):
        print('Restart command loaded')


def setup(client):
    client.add_cog(Restart(client))
