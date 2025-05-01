from discord import slash_command, Embed
from discord.ext import commands

from Helpers.classes import Guild
from Helpers.database import DB
from Helpers.functions import getGuildMembers
from Helpers.variables import test, discord_ranks


class RankCheck(commands.Cog):
    def __init__(self, client):
        self.client = client

    if test:
        guilds = [1364751619018850405]
    else:
        guilds = [784795827808763904, 1364751619018850405]

    @slash_command(description='Check for game/discord rank mismatch', guild_ids=guilds)
    async def rankcheck(self, message):
        await message.defer()
        db = DB()
        db.connect()
        data = Guild('The%20Aquarium').all_members
        all_data = '```ansi\n [1;37m{:^16s}   {:^12s}   {:^23s} ' \
                   '\n╘═════════════════╪══════════════╪════════════════════════╛\n'.format('Player', 'In-Game Rank',
                                                                                            'Discord Rank')
        for member in data:
            db.cursor.execute(f'SELECT * FROM discord_links WHERE ign = \'{member["name"]}\'')
            row = db.cursor.fetchone()
            if row is not None and row[4] != 'None':
                if member['rank'].upper() != discord_ranks[row[4]]['in_game_rank']:
                    discord_rank = f'{row[4]} ({discord_ranks[row[4]]["in_game_rank"]})'
                    all_data = all_data + f'[0;0m {member["name"]:16} [1;37m│ [0;0m{member["rank"].upper():12} [1;37m│ [0;0m{discord_rank:23}\n'
            else:
                all_data = all_data + f'[0;0m {member["name"]:16} [1;37m│ [0;0m{member["rank"].upper():12} [1;37m│ [2;31mNOT LINKED\n'
        embed = Embed(title='Rank mismatches', description=all_data + '```')
        await message.respond(embed=embed)
        db.close()

    @commands.Cog.listener()
    async def on_ready(self):
        print('RankCheck command loaded')


def setup(client):
    client.add_cog(RankCheck(client))
