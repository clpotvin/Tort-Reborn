import discord
from discord.ext import commands
from discord.commands import slash_command
import random
import json
import urllib.request
import re


class Fish(commands.Cog):
    def __init__(self, client):
        self.client = client

    @slash_command(description='Sends a random fish fact')
    async def fish(self, message):
        await message.defer()
        url = 'https://www.fishwatch.gov/api/species'

        f = urllib.request.urlopen(url)
        data = f.read().decode('utf-8')

        fish = json.loads(data)
        randfish = random.randint(0, len(fish))

        name = fish[randfish]['Species Name']
        bio = re.sub('<.*?>', '', fish[randfish]['Biology'])
        image = fish[randfish]['Image Gallery'][0]['src']

        embed = discord.Embed(title=name, description=bio)
        embed.set_image(url=image)

        await message.respond(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self):
        print('Fish command loaded')


def setup(client):
    client.add_cog(Fish(client))
