import json
import time

import discord
from discord import Embed
from discord.ext import commands
from discord.ui import View, Button

from Helpers.database import DB
from Helpers.functions import getPlayerUUID
from Helpers.variables import guilds, test


class OnGuildChannelUpdate(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        db = DB()
        db.connect()
        db.cursor.execute(f'SELECT * FROM new_app WHERE channel = {before.id}')
        rows = db.cursor.fetchall()
        if len(rows) > 0:
            if test:
                channel = self.client.get_channel(1004096609333817375)
            else:
                channel = self.client.get_channel(889162191150931978)
            player_uuid = rows[0][9]
            username = False
            embed_image = False
            msg = await channel.fetch_message(rows[0][6])
            if player_uuid != '':
                username, UUID = getPlayerUUID(player_uuid)
            if after.category.name == 'Guild Queue':
                status = ":hourglass: In Queue"
            elif after.category.name == 'Invited':
                status = ":hourglass: Invited"
            else:
                status = after.name.split('-')[0]
                match status:
                    case "closed":
                        status = ":lock: Closed"
                    case "ticket":
                        status = ":green_circle: Opened"
                    case "accepted":
                        status = ":white_check_mark: Accepted"
                    case "denied":
                        status = ":x: Denied"
                    case "na":
                        status = ":grey_question: N/A"
                    case _:
                        status = status.capitalize()

            if status in [":hourglass: In Queue", ":hourglass: Invited"]:
                colour = 0xffe019
            elif status != ":green_circle: Opened":
                colour = 0xd93232
            else:
                colour = 0x3ed63e

            embed_description = ''

            if username:
                embed_title = f'Application {rows[0][2].replace("ticket-", "")} ({username})'
                with open('blacklist.json', 'r') as f:
                    blacklist = json.load(f)
                    f.close()

                for player in blacklist:
                    if UUID == player['UUID']:
                        embed_description = f':no_entry: Player present on blacklist!\n**Name:** {username}\n**UUID:** {UUID}'
            else:
                embed_title = f'Application {rows[0][2].replace("ticket-", "")}'

            embed = discord.Embed(title=embed_title, description=embed_description, colour=colour)
            embed.add_field(name='Channel', value=f':link: <#{rows[0][0]}>')
            embed.add_field(name='Status', value=status)
            if player_uuid != '':
                embed.set_image(url=f'attachment://{rows[0][2].replace("ticket-", "")}-{player_uuid}.png')
            await msg.edit(f'<@&870767928704921651>', embed=embed)
            db.cursor.execute(
                f'UPDATE new_app SET status = \'{status}\' WHERE channel = \'{before.id}\'')
            db.connection.commit()
        db.close()

    @commands.Cog.listener()
    async def on_ready(self):
        print('OnGuildChannelUpdate event loaded')


def setup(client):
    client.add_cog(OnGuildChannelUpdate(client))
