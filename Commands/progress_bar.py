import time
from io import BytesIO

from discord.ext import commands
from discord.commands import slash_command
import discord

from Helpers.functions import generate_rank_badge, create_progress_bar


class ProgressBar(commands.Cog):
    def __init__(self, client):
        self.client = client

    @slash_command(guilds=[1053447772302479421])
    async def progress_bar(self, message, width: discord.Option(int, require=True),
                           percentage: discord.Option(int, min_value=0, max_value=100, require=True)):
        img = create_progress_bar(width, percentage)

        with BytesIO() as file:
            img.save(file, format="PNG")
            file.seek(0)
            t = int(time.time())
            rankbadge = discord.File(file, filename=f"bar{t}.png")

        await message.respond(file=rankbadge)

    @commands.Cog.listener()
    async def on_ready(self):
        print('ProgressBar command loaded')


def setup(client):
    client.add_cog(ProgressBar(client))
