from io import BytesIO

import discord.types.member
from PIL import Image, ImageDraw, ImageFont
from discord import Embed
from discord.ext import commands
from discord.ui import View, Button

from Helpers.database import DB
from Helpers.variables import guilds


class formView(View):
    def __init__(self, channel):
        super().__init__()
        self.add_item(Button(label='Guild Member', url=f'https://tally.so/r/3laAPp?ticket={channel}', emoji='🔵'))
        self.add_item(Button(label='Community Member', url=f'https://tally.so/r/mBk0l7?ticket={channel}', emoji='🟢'))


class OnGuildChannelCreate(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if channel.name.startswith('ticket-') and channel.guild.id == guilds[0] and channel.category.name == 'Guild Applications':
            db = DB()
            db.connect()
            webhook = await channel.create_webhook(name=channel.name)
            db.cursor.execute(
                f'INSERT INTO new_app (channel,posted,ticket,webhook) VALUES (\'{channel.id}\', False, \'{channel.name}\',\'{webhook.url}\');')
            db.connection.commit()
            db.close()
            user_name = ''
            for overwrite in channel.overwrites:
                if type(overwrite) == discord.member.Member:
                    if not overwrite.bot:
                        user_name = overwrite.name
                        break
            img = Image.open('images/profile/welcome.png')
            draw = ImageDraw.Draw(img)
            gameFont = ImageFont.truetype('images/profile/game.ttf', 38)
            draw.text((198, 13), user_name, font=gameFont, fill='#ffba02')

            with BytesIO() as file:
                img.save(file, format="PNG")
                file.seek(0)
                welcome_message = discord.File(file, filename=f"welcome_{channel.id}.png")

            await channel.send('', view=formView(channel.id), file=welcome_message)


    @commands.Cog.listener()
    async def on_ready(self):
        print('OnGuildChannelCreate event loaded')


def setup(client):
    client.add_cog(OnGuildChannelCreate(client))
