import datetime

import discord
import json
import math

from dateutil import parser
from discord.ext import pages
from Helpers.variables import rank_map
from Helpers.functions import isInCurrDay, getGuildMembers
from discord.ext import commands
from discord.commands import slash_command


class Playtime(commands.Cog):
    def __init__(self, client):
        self.client = client

    @slash_command(description='Displays a playtime leaderboard for specified time period (Default 7 days)')
    async def playtime(self, message, days: int = 7, reversed: bool = False):
        await message.defer()
        book = []
        with open('player_activity.json', 'r') as f:
            old_data = json.loads(f.read())
        with open('current_activity.json', 'r') as f:
            new_data = json.loads(f.read())

        taq = getGuildMembers('The%20Aquarium')

        if days > len(old_data):
            days = len(old_data)
        elif days < 1:
            days = 1
        playerdata = []
        for member in new_data:
            uuid = member['uuid']
            playtime = member['playtime']
            day = days
            while not isInCurrDay(old_data[day - 1]['members'], uuid) and day - 1 != 0:
                day -= 1
            else:
                for user in old_data[day - 1]['members']:
                    found = False
                    for player in taq:
                        if player['uuid'] == user['uuid']:
                            joined_date = parser.isoparse(player['joined'])
                            member_for = datetime.datetime.now() - joined_date.replace(tzinfo=None)
                            found = True
                            continue
                    if not found:
                        member_for = datetime.datetime.now() - datetime.datetime.now()
                    if uuid == user['uuid']:
                        real_pt = playtime - user['playtime']
                        if day != days:
                            playerdata.append(
                                {'name': member['name'], 'uuid': uuid, 'playtime': real_pt, 'rank': member['rank'],
                                 'warning': True, 'member_for': member_for.days})
                        else:
                            playerdata.append(
                                {'name': member['name'], 'uuid': uuid, 'playtime': real_pt, 'rank': member['rank'],
                                 'warning': False, 'member_for': member_for.days})

        if reversed:
            if playerdata:
                i = len(playerdata)
                playerdata.sort(key=lambda x: x['playtime'], reverse=False)
                page_num = int(math.ceil(len(playerdata) / 30))
                for page in range(page_num):
                    all_data = '```ansi\n [1;37mPos.   Rank    {:^17s}   {:^10s}    {:^10s} ' \
                               '\n╘═════╪═══════╪═══════════════════╪════════════╪═══════════╛\n'.format(
                                'Player Name', 'Playtime', 'Member for')
                    page_playerdata = playerdata[(30 * page):30 + (30 * page)]
                    for player in page_playerdata:
                        if player['playtime'] >= 0:
                            if player['warning']:
                                all_data = all_data + (
                                    '[0;36m {:4s} [1;37m│ [0;36m{:5s} [1;37m│ [0;36m{:17s} [1;37m│ [0;36m{:10s} │ [0;36m{:9s} '
                                    '\n'.format(
                                        f'{i}.', rank_map[player['rank']], player['name'],
                                        str(int((player['playtime'] * 4.7) // 60)) + ' hours', str(player['member_for']) + ' days'))
                            else:
                                all_data = all_data + (
                                    '[0;0m [0;0m{:4s} [1;37m│ [0;0m{:5s} [1;37m│ [0;0m{:17s} [1;37m│ [0;0m{:10s} │ [0;0m{:9s} '
                                    '\n'.format(
                                        f'{i}.', rank_map[player['rank']], player['name'],
                                        str(int((player['playtime'] * 4.7) // 60)) + ' hours', str(player['member_for']) + ' days'))
                        else:
                            pass
                        i -= 1
                    all_data += '```'
                    embed = discord.Embed(title='TAq activity for the past ' + str(days) + ' days',
                                          description=all_data)
                    embed.set_footer(text='# marked have not been in the guild for the requested amount of time')
                    book.append(embed)
        else:
            if playerdata:
                i = 1
                playerdata.sort(key=lambda x: x['playtime'], reverse=True)
                page_num = int(math.ceil(len(playerdata) / 30))
                for page in range(page_num):
                    all_data = '```ansi\n [1;37mPos.   Rank    {:^17s}   {:^10s}   {:^10s} ' \
                               '\n╘═════╪═══════╪═══════════════════╪════════════╪═══════════╛\n'.format(
                                'Player Name', 'Playtime', 'Member for')
                    page_playerdata = playerdata[(30 * page):30 + (30 * page)]
                    for player in page_playerdata:
                        player_playtime = int((player['playtime'] * 4.7) // 60)
                        if player_playtime == 1:
                            hr = ' hour'
                        else:
                            hr = ' hours'
                        if 60 > player['playtime'] * 4.7 > 0:
                            player_playtime = '<1'
                            hr = ' hour'
                        if player['playtime'] >= 0:
                            if player['warning']:
                                all_data = all_data + (
                                    '[0;36m {:4s} [1;37m│ [0;36m{:5s} [1;37m│ [0;36m{:17s} [1;37m│ [0;36m{:10s} │ [0;36m{:9s} '
                                    '\n'.format(
                                        f'{i}.', rank_map[player['rank']], player['name'],
                                        str(int((player['playtime'] * 4.7) // 60)) + ' hours', str(player['member_for']) + 'days'))
                            else:
                                all_data = all_data + (
                                    '[0;0m [0;0m{:4s} [1;37m│ [0;0m{:5s} [1;37m│ [0;0m{:17s} [1;37m│ [0;0m{:10s} │ [0;0m{:9s} '
                                    '\n'.format(
                                        f'{i}.', rank_map[player['rank']], player['name'],
                                        str(int((player['playtime'] * 4.7) // 60)) + ' hours', str(player['member_for']) + ' days'))
                        else:
                            pass
                        i += 1
                    all_data += '```'
                    embed = discord.Embed(title='TAq activity for the past ' + str(days) + ' days',
                                          description=all_data)
                    embed.set_footer(text='# marked have not been in the guild for the requested amount of time')
                    book.append(embed)
        final_book = pages.Paginator(pages=book)
        await final_book.respond(message.interaction)

    @commands.Cog.listener()
    async def on_ready(self):
        print('Playtime command loaded')


def setup(client):
    client.add_cog(Playtime(client))
