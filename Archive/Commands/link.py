import json
import urllib.request

import discord
from discord import slash_command, Embed
from discord.ext import commands
from discord.ui import Modal, InputText, Button, View

from Helpers.database import DB


class LinkModal(Modal):
    def __init__(self, client, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(InputText(label="Authentication code"))
        self.client = client

    async def callback(self, interaction: discord.Interaction):
        db = DB()
        db.connect()
        user_id = interaction.user.id
        try:
            user_nick = interaction.user.nick.split(' ')
        except:
            user_nick = ['']
        request = urllib.request.urlopen(f'https://auth.aristois.net/token/{self.children[0].value}')
        data = request.read().decode('utf-8')
        jsondata = json.loads(data)
        db.cursor.execute(f'SELECT * FROM discord_links WHERE discord_id = {user_id}')
        rows = db.cursor.fetchall()
        if jsondata['status'] == 'success':
            if len(rows) == 0:
                db.cursor.execute(
                    f'INSERT INTO discord_links (discord_id, ign, linked) VALUES ({user_id}, \'{jsondata["username"]}\', 1, {user_nick[0]});')
                db.connection.commit()
                await interaction.response.send_message(f"**{jsondata['username']}** has been successfully linked to your "
                                                        f"discord.", ephemeral=True)
            else:
                if rows[0][2] == 0:
                    db.cursor.execute(
                        f'UPDATE discord_links SET ign = \'{jsondata["username"]}\', linked = 1 WHERE discord_id = {user_id}')
                    db.connection.commit()
                    await interaction.response.send_message(
                        f"**{jsondata['username']}** has been successfully linked to your "
                        f"discord.", ephemeral=True)
                else:
                    db.cursor.execute(
                        f'UPDATE discord_links SET ign = \'{jsondata["username"]}\', linked = 1 WHERE discord_id = {user_id}')
                    db.connection.commit()
                    await interaction.response.send_message(
                        f"**{jsondata['username']}** has been successfully linked to your "
                        f"discord.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Something went wrong. Please try again later.", ephemeral=True)
        db.close()


class Link(commands.Cog):
    def __init__(self, client):
        self.client = client

    @slash_command(description='Link your Discord account to your minecraft account.')
    async def link(self, message):
        embed = Embed(title='How to link you minecraft account', description='Simply join the server '
                                                                             '**auth.aristois.net** and '
                                                                             'get your auth code.\n\nOnce you obtain '
                                                                             'your code '
                                                                             'click the **I\'m ready!** button down '
                                                                             'below and '
                                                                             'enter your code.')
        link_button = Button(label='I\'m ready!', style=discord.ButtonStyle.primary)

        async def button_callback(interaction):
            modal = LinkModal(self.client, title="Discord linking")
            await interaction.response.send_modal(modal)

        link_button.callback = button_callback
        view = View()
        view.add_item(link_button)
        await message.interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        print('Link command loaded')


def setup(client):
    client.add_cog(Link(client))
