import dateutil.parser
import discord
from discord.ext import commands
from discord.ext import pages
from discord.commands import slash_command
from Helpers.functions import date_diff
from Helpers.variables import rank_map
import json
import math


class Inactivity(commands.Cog):
    def __init__(self, client):
        self.client = client

    @slash_command(description='Displays an inactivity of members')
    async def inactivity(self, message, reversed: bool = False):
        await message.defer()
        book = []
        # new_data = await getGuildActivity(message.channel)
        with open('current_activity.json', 'r') as f:
            new_data = json.loads(f.read())
        playerdata = []
        for member in new_data:
            uuid = member['uuid']
            last_join = member['last_join']
            last_seen = date_diff(dateutil.parser.isoparse(last_join))
            playerdata.append(
                    {'name': member['name'], 'uuid': uuid, 'last_join': last_seen, 'rank': member['rank']})
        if reversed:
            if playerdata:
                i = len(playerdata)
                playerdata.sort(key=lambda x: x['last_join'], reverse=False)
            page_num = int(math.ceil(len(playerdata) / 30))
            for page in range(page_num):
                page_playerdata = playerdata[(30 * page):30 + (30 * page)]
                all_data = '```cs\n Pos.   Rank    {:^17s}   Inactivity ' \
                           '\n╘═════╪═══════╪═══════════════════╪═══════════╛\n'.format(
                            'Player Name')
                for player in page_playerdata:
                    all_data = all_data + (
                        ' {:4s} │ {:5s} │ {:17s} │ {:10s} \n'.format(f'{i}.', rank_map[player['rank']], player['name'],
                                                                     str(player['last_join']) + ' days'))
                    i -= 1
                all_data += '```'
                book.append(discord.Embed(title='TAq inactivity', description=all_data))
        else:
            if playerdata:
                i = 1
                playerdata.sort(key=lambda x: x['last_join'], reverse=True)
            page_num = int(math.ceil(len(playerdata) / 30))
            for page in range(page_num):
                page_playerdata = playerdata[(30 * page):30 + (30 * page)]
                all_data = '```cs\n Pos.   Rank    {:^17s}   Inactivity ' \
                           '\n╘═════╪═══════╪═══════════════════╪═══════════╛\n'.format( 
                            'Player Name')
                for player in page_playerdata:
                    all_data = all_data + (
                        ' {:4s} │ {:5s} │ {:17s} │ {:10s} \n'.format(f'{i}.', rank_map[player['rank']], player['name'],
                                                                     str(player['last_join']) + ' days'))
                    i += 1
                all_data += '```'
                book.append(discord.Embed(title='TAq inactivity', description=all_data))

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
        print('Inactivity command loaded')


def setup(client):
    client.add_cog(Inactivity(client))
