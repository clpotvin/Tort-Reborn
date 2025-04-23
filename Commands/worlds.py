import discord
from discord.ext import commands
from discord.commands import slash_command
from discord.ext import pages
import json
import urllib.request
import time
import datetime
import math


class Worlds(commands.Cog):
    def __init__(self, client):
        self.client = client

    @slash_command(description='Shows worlds information')
    async def worlds(self, message,
                     order_by: discord.Option(str, choices=['World', 'Player count', 'World age', 'Next soul point'],
                                              require=True),
                     order: discord.Option(str, choices=['⬆️ Ascending', '⬇️ Descending'], require=True)):
        await message.defer()
        url = 'https://athena.wynntils.com/cache/get/serverList'

        f = urllib.request.urlopen(url)
        data = f.read().decode('utf-8')
        book = []
        worlds = json.loads(data)
        worlds_sp = []
        if not worlds:
            embed = discord.Embed(title='🌍 All worlds are currently offline', description='')
            await message.respond(embed=embed)
            return
        for world in worlds['servers']:
            if world == 'YT':
                continue
            timediff = int(time.time()) - (int(worlds['servers'][world]['firstSeen'] / 1000))
            worlds_sp.append({'world_name': world, 'world': int(world.replace('WC', '')),
                              'player_count': len(worlds['servers'][world]['players']), 'world_age': timediff,
                              'next_soul_point': 1200 - (timediff % 1200)})

        worlds_sp.sort(key=lambda x: x[order_by.lower().replace(' ', '_')],
                       reverse=False if order == '⬆️ Ascending' else True)

        page_num = math.ceil(len(worlds_sp) / 30)
        for page in range(page_num):
            alltimes = '```ml\n World   Player Count   World Age   Next Soul Point ' \
                       '\n╘══════╪══════════════╪═══════════╪════════════════╛\n'
            worlds_page = worlds_sp[(30 * page):30 + (30 * page)]
            for world in worlds_page:
                world_age = str(datetime.timedelta(seconds=world['world_age']))
                next_sp = str(datetime.timedelta(seconds=world['next_soul_point']))
                alltimes = alltimes + ' {:5s} │ {:^12s} │ {:^9s} │ {:^15s}\n'.format(world["world_name"],
                                                                                     str(world['player_count']) + '/55',
                                                                                     world_age, next_sp[2::])

            alltimes = alltimes + ' {:5s} │ {:^12s} │ {:^9s} │ {:^15s} ```\n'.format('', '', '', '(~1 minute)')
            embed = discord.Embed(title=f'Worlds ordered by {order_by}', description=alltimes)
            book.append(embed)

        final_book = pages.Paginator(pages=book)
        final_book.add_button(
            pages.PaginatorButton("prev", emoji="<:left_arrow:1198703157501509682>", style=discord.ButtonStyle.red))
        final_book.add_button(
            pages.PaginatorButton("next", emoji="<:right_arrow:1198703156088021112>", style=discord.ButtonStyle.green))
        final_book.add_button(pages.PaginatorButton("first", emoji="<:first_arrows:1198703152204103760>",
                                                    style=discord.ButtonStyle.blurple))
        final_book.add_button(pages.PaginatorButton("last", emoji="<:last_arrows:1198703153726627880>",
                                                    style=discord.ButtonStyle.blurple))
        await final_book.respond(message.interaction)

    @commands.Cog.listener()
    async def on_ready(self):
        print('Worlds command loaded')


def setup(client):
    client.add_cog(Worlds(client))
