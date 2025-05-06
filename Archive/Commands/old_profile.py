import time
from io import BytesIO

import discord
import requests
from PIL import Image
from discord import default_permissions
from discord.ext import commands
from discord.commands import slash_command
import json
import dateutil.parser
import datetime

from Helpers.database import cur
from Helpers.functions import getPlayerData, getData, pretty_date, dropShadow, getPlayerUUID
from Helpers.variables import rank_color_map, star_rank_map, discord_ranks, discord_star_rank_map, \
    discord_rank_color_map


class Profile(commands.Cog):
    def __init__(self, client):
        self.client = client

    @slash_command(description='Displays a guild profile of guild member')
    async def profile(self, message, name: discord.Option(str, require=True), days: int = 7):
        await message.defer()
        easter_egg = False
        if name == '💧':
            easter_egg = True
            name = 'Aqualost'
        player = getPlayerUUID(name)
        pdata = getPlayerData(player[1])['data'][0]
        guild_members = []
        for member in getData('The Aquarium'):
            guild_members.append(member['uuid'])
        if pdata['uuid'] not in guild_members:
            if pdata['username'] != 'Maracs':
                embed = discord.Embed(title=':no_entry: Something went wrong',
                                      description=pdata['username'].replace('_', '\_') + ' really should join TAq!', color=0xe33232)
            else:
                embed = discord.Embed(title=':no_entry: Something went wrong',
                                      description=pdata['username'] + ' really should stay away from TAq!', color=0xe33232)
            await message.respond(embed=embed)
        else:
            gdata = getData('The Aquarium')
            for guildee in gdata:
                if guildee['uuid'] == pdata['uuid']:
                    guildstats = guildee
                else:
                    pass
            cur.execute(f'SELECT * FROM discord_links WHERE ign = \'{pdata["username"]}\'')
            rows = cur.fetchall()
            if len(rows) != 0:
                linked = True
                try:
                    user_rank = discord_star_rank_map[rows[0][3]]
                    color = discord_rank_color_map[rows[0][3]]
                except:
                    user_rank = star_rank_map[guildstats['rank']]
                    color = rank_color_map[guildstats['rank']]
                description = f'<:discord:1026929770216292462> <@{rows[0][0]}>\n'
            else:
                linked = False
                user_rank = star_rank_map[guildstats['rank']]
                color = rank_color_map[guildstats['rank']]
                description = ''

            cur.execute(f'SELECT * FROM shells WHERE \"user\" = \'{pdata["username"]}\'')
            rows = cur.fetchall()

            if len(rows) == 0:
                shells = 0
            else:
                shells = rows[0][1]

            description += f'<:shell:1026922275196375051> **Shells:** {shells}'
            if pdata['meta']['location']['online']:
                description = f'<:world:1028786718649892885> **{pdata["meta"]["location"]["server"]}**\n\n' + description
                if easter_egg:
                    embed = discord.Embed(
                        title=f'<:tortemoji:919659913054130196> {user_rank} {pdata["username"]}',
                        description=f'{description}\n⠀', color=0x4287f5)
                else:
                    if pdata["username"] == "Maracs":
                        embed = discord.Embed(
                            title=f'<:online:1026922270553284738> {user_rank} Idiot',
                            description=f'{description}\n⠀', color=color)
                    else:
                        usr = pdata["username"].replace("_","\_")
                        embed = discord.Embed(
                        title=f'{user_rank}\n<:online:1026922270553284738> {usr}',
                        description=f'{description}\n⠀', color=color)
            else:
                lastjoined = dateutil.parser.isoparse(pdata['meta']['lastJoin'])
                description = f"<:inactive:1026922267847970836> Last seen {pretty_date(lastjoined)}\n\n" + description
                if easter_egg:
                    embed = discord.Embed(title=f'❤ {user_rank} {pdata["username"]}', description=f'{description}\n⠀',
                                          color=0x4287f5)
                else:
                    if pdata["username"] == "Maracs":
                        embed = discord.Embed(
                        title=f'<:offline:1026922269043331274> {user_rank} Idiot',
                        description=f'{description}\n⠀', color=color)
                    else:
                        usr = pdata["username"].replace("_","\_")
                        embed = discord.Embed(
                            title=f'<:offline:1026922269043331274> {usr}',
                            description=f'{user_rank}\n\n{description}\n⠀', color=color)
            profile_pictures = json.load(open('backgrounds.json', 'r'))
            if player[1] in profile_pictures:
                skin_url = 'https://visage.surgeplay.com/bust/300/' + pdata['uuid']
                skin_data = requests.get(skin_url)
                skin = Image.open(BytesIO(skin_data.content))

                shadow = dropShadow(skin)
                background = Image.open(f"images/profile_pictures/{profile_pictures[player[1]]}")
                background.paste(shadow, (0, 0), shadow)
                background.paste(skin, (25, 50), skin)

                with BytesIO() as file:
                    background.save(file, format="PNG")
                    file.seek(0)
                    t = int(time.time())
                    skinimage = discord.File(file, filename=f"profile{t}.png")
                    embed.set_thumbnail(url=f"attachment://profile{t}.png")
            else:
                embed.set_thumbnail(url='https://visage.surgeplay.com/bust/350/' + pdata['uuid'])

            joined = dateutil.parser.isoparse(guildstats['joined'])
            in_guild_for = datetime.datetime.now() - joined.replace(tzinfo=None)

            with open('activity2.json', 'r') as f:
                old_data = json.loads(f.read())
            if days > len(old_data):
                days = len(old_data)
            if days > in_guild_for.days:
                days = in_guild_for.days
            if days < 1:
                days = 1
            for member in old_data[days - 1]['members']:
                if pdata['uuid'] == member['uuid']:
                    real_pt = pdata['meta']['playtime'] - member['playtime']
                    real_xp = guildstats['contributed'] - member['contributed']
            embed.add_field(name='<:total_xp:1026926626967134289> Total XP Contributed',
                            value='{:,}'.format(guildstats['contributed']))
            embed.add_field(name='<:member:1026922273128595536> TAq member for', value=str(in_guild_for.days) + ' days')
            embed.add_field(name='─────────\nPast ' + str(days) + ' days:',
                            value='<:time:1026922271811584020> **Playtime**: ' + str(
                                int((
                                                real_pt * 4.7) // 60)) + ' hours\n<:XP:1026922274441400381> **XP Contributed**: ' + '{:,}'.format(
                                real_xp) + " XP",
                            inline=False)
            if not linked:
                embed.set_footer(text='Some data could be more accurate. Link you minecraft account using the /link command or tell our moderators to link it for you.', icon_url='https://media.discordapp.net/attachments/1004096609686143008/1039684902754455612/image.png?width=671&height=671')
            if 'skinimage' not in locals():
                await message.respond(embed=embed)
            else:
                await message.respond(embed=embed, file=skinimage)

    @commands.Cog.listener()
    async def on_ready(self):
        print('Profile command loaded')


def setup(client):
    client.add_cog(Profile(client))
