import os
import time
from datetime import datetime
from io import BytesIO

import discord
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
from discord import SlashCommandGroup, default_permissions
from discord.ext import commands
from discord.ui import Modal, InputText

from Helpers.classes import LinkAccount, PlayerStats, PlayerShells
from Helpers.database import DB
from Helpers.functions import addLine, split_sentence, expand_image, getPlayerUUID
from Helpers.variables import guilds, discord_ranks, discord_rank_roles


class ShellModalName(Modal):
    def __init__(self, user, operation, amount, reason, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.user = user
        self.operation = operation
        self.amount = amount
        self.reason = reason
        self.add_item(InputText(label="Player's Name", placeholder="Player's In-Game Name without rank"))

    async def callback(self, interaction: discord.Interaction):
        db = DB()
        db.connect()

        img = Image.new('RGBA', (375, 95), color='#100010e2')
        d = ImageDraw.Draw(img)
        d.fontmode = '1'
        gameFont = ImageFont.truetype('images/profile/game.ttf', 19)
        player = PlayerStats(self.children[0].value, 1)
        # skin
        try:
            url = f"https://visage.surgeplay.com/bust/75/{player.UUID}"
            response = requests.get(url)
            skin = Image.open(BytesIO(response.content))
        except:
            skin = Image.open('images/profile/x-steve.webp')
        img.paste(skin, (10, 10), skin)

        if self.operation == 'add':
            new_amount = self.amount
            difference = f'&a+{self.amount}' if self.amount > 0 else f'&c{self.amount}'
            addLine(f'&7All-Time: &f{new_amount} &7({difference}&7)', d, gameFont, 95, 61)
        else:
            new_amount = self.amount * -1
            difference = f'&c-{self.amount}' if self.amount > 0 else f'&a+{self.amount * -1}'
            addLine(f'&7All-Time: 0', d, gameFont, 95, 61)
        db.cursor.execute(
            f'INSERT INTO discord_links (discord_id, ign, linked, rank) VALUES ({self.user.id}, \'{self.children[0].value}\', 0, \'\');')
        db.cursor.execute(
            f'INSERT INTO shells (user, shells) VALUES (\'{self.children[0].value}\', {new_amount});')
        db.connection.commit()

        addLine(f'&f{player.username}', d, gameFont, 95, 15)
        addLine(f'&7Balance: &f{new_amount} &7({difference}&7)', d, gameFont, 95, 40)

        if self.reason != '':
            reasonLines = split_sentence(self.reason)
            for line in reasonLines:
                img, d = expand_image(img)
                addLine(f'&3{line}', d, gameFont, 10, img.height - 25)

        # await interaction.response.send_message(
        #     f'Added {self.amount} shells to {self.children[0].value}', ephemeral=True)

        img = ImageOps.expand(img, border=(2, 2), fill='#100010e2')
        d = ImageDraw.Draw(img)

        d.rectangle((2, 2, img.width - 3, img.height - 3), outline='#240059', width=2)
        d.rectangle((0, 0, 1, 1), fill='#00000000')
        d.rectangle((img.width - 2, 0, img.width, 1), fill='#00000000')
        d.rectangle((0, img.height - 2, 1, img.height), fill='#00000000')
        d.rectangle((img.width - 2, img.height - 2, img.width, img.height), fill='#00000000')

        with BytesIO() as file:
            img.save(file, format="PNG")
            file.seek(0)
            t = int(time.time())
            shell_img = discord.File(file, filename=f"shell{t}.png")

        await interaction.response.send_message(file=shell_img)

        db.close()


class Manage(commands.Cog):
    def __init__(self, client):
        self.client = client

    manage_group = SlashCommandGroup('manage', 'Guild management commands', guild_ids=guilds, default_member_permissions=discord.Permissions(manage_roles=True))

    @manage_group.command()
    async def rank(self, message, user: discord.Member,
                   rank: discord.Option(str, choices=['Starfish', 'Manatee', 'Piranha',
                                                      'Barracuda', 'Angler',
                                                      'Hammerhead',
                                                      'Sailfish', 'Dolphin',
                                                      'Narwhal'])):
        db = DB()
        db.connect()
        removed = 'Removed Roles:'
        added = 'Added Roles:'
        all_roles = message.interaction.guild.roles

        await message.defer(ephemeral=True)

        for add_role in discord_ranks[rank]['roles']:
            role = discord.utils.find(lambda r: r.name == add_role, all_roles)
            if role not in user.roles:
                curr_role = discord.utils.get(all_roles, name=add_role)
                await user.add_roles(curr_role)
                added = f'{added}\n - {add_role}'

        remove_roles = [x for x in discord_rank_roles if x not in discord_ranks[rank]['roles']]
        for remove_role in remove_roles:
            role = discord.utils.find(lambda r: r.name == remove_role, all_roles)
            if role in user.roles:
                curr_role = discord.utils.get(all_roles, name=remove_role)
                await user.remove_roles(curr_role)
                removed = f'{removed}\n - {remove_role}'

        db.cursor.execute(f'SELECT * FROM discord_links WHERE discord_id = {user.id}')
        rows = db.cursor.fetchall()
        if len(rows) != 0:
            db.cursor.execute(f'UPDATE discord_links SET rank = \'{rank}\' WHERE discord_id = {user.id}')
            db.connection.commit()
            await user.edit(nick=f'{rank} {rows[0][1]}')
        else:
            modal = LinkAccount(title="Link User to Minecraft IGN", user=user, rank=rank, added=added, removed=removed)
            await message.interaction.response.send_modal(modal)
        await message.respond(f'{added}\n\n{removed}')
        db.close()

    @manage_group.command()
    async def shells(self, message, operation: discord.Option(str, choices=['add', 'remove']), user: discord.Member,
                     amount: int, reason: discord.Option(str, required=False, default='')):
        db = DB()
        db.connect()
        db.cursor.execute(f'SELECT * FROM discord_links WHERE discord_id = \'{user.id}\'')
        rows = db.cursor.fetchall()
        if len(rows) != 0:
            player = PlayerShells(user.id)
            await message.defer()
            img = Image.new('RGBA', (375, 95), color='#100010e2')
            d = ImageDraw.Draw(img)
            d.fontmode = '1'
            gameFont = ImageFont.truetype('images/profile/game.ttf', 19)
            # skin
            try:
                headers = {'User-Agent': os.getenv("visage_UA")}
                url = f"https://visage.surgeplay.com/bust/75/{player.UUID}"
                response = requests.get(url, headers=headers)
                skin = Image.open(BytesIO(response.content))
            except:
                skin = Image.open('images/profile/X-Steve.webp')
            img.paste(skin, (10, 10), skin)

            if not player.error:
                if operation == 'add':
                    difference = f'&a+{amount}' if amount > 0 else f'&c{amount}'
                    new_total = player.shells + amount
                    new_amount = player.balance + amount
                    db.cursor.execute(f'UPDATE shells SET shells = {new_total}, bal = {new_amount} WHERE user = \'{user.id}\'')
                    addLine(f'&7All-Time: &f{new_total} &7({difference}&7)', d, gameFont, 95, 61)
                else:
                    difference = f'&c-{amount}' if amount > 0 else f'&a+{amount*-1}'
                    new_amount = player.balance - amount
                    db.cursor.execute(f'UPDATE shells SET bal = {new_amount} WHERE user = \'{user.id}\'')
                    addLine(f'&7All-Time: &f{player.shells}', d, gameFont, 95, 61)

                addLine(f'&f{player.username}', d, gameFont, 95, 15)
                addLine(f'&7Balance: &f{new_amount} &7({difference}&7)', d, gameFont, 95, 40)

            else:
                if operation == 'add':
                    new_amount = amount
                    difference = f'&a+{amount}' if amount > 0 else f'&c{amount}'
                    db.cursor.execute(
                        f'INSERT INTO shells (user, shells, bal) VALUES (\'{user.id}\', {new_amount}, {new_amount});')
                    addLine(f'&7All-Time: &f{new_amount} &7({difference}&7)', d, gameFont, 95, 61)
                else:
                    new_amount = amount*-1
                    difference = f'&c-{amount}' if amount > 0 else f'&a+{amount * -1}'
                    db.cursor.execute(
                        f'INSERT INTO shells (user, shells, bal) VALUES (\'{user.id}\', 0, {new_amount});')
                    addLine(f'&7All-Time: 0', d, gameFont, 95, 61)

                addLine(f'&f{player.username}', d, gameFont, 95, 15)
                addLine(f'&7Balance: &f{new_amount} &7({difference}&7)', d, gameFont, 95, 40)

            if reason != '':
                reasonLines = split_sentence(reason)
                for line in reasonLines:
                    img, d = expand_image(img)
                    addLine(f'&3{line}', d, gameFont, 10, img.height - 25)

            db.connection.commit()
            preposition = 'to' if operation == 'add' else 'from'
            with open('shell.log', 'a') as f:
                curr_datetime = datetime.now()
                curr_datetime_str = curr_datetime.strftime("%d/%m/%Y, %H:%M:%S")
                f.write(
                    f'[{curr_datetime_str}] {message.author.name} {operation[:5]}ed {amount} shells {preposition} {player.username}. Reason: {reason}\n')
                f.close()

            img = ImageOps.expand(img, border=(2, 2), fill='#100010e2')
            d = ImageDraw.Draw(img)

            d.rectangle((2, 2, img.width - 3, img.height - 3), outline='#240059', width=2)
            d.rectangle((0, 0, 1, 1), fill='#00000000')
            d.rectangle((img.width - 2, 0, img.width, 1), fill='#00000000')
            d.rectangle((0, img.height - 2, 1, img.height), fill='#00000000')
            d.rectangle((img.width - 2, img.height - 2, img.width, img.height), fill='#00000000')

            with BytesIO() as file:
                img.save(file, format="PNG")
                file.seek(0)
                t = int(time.time())
                shell_img = discord.File(file, filename=f"shell{t}.png")

            await message.respond(file=shell_img)
        else:
            modal = ShellModalName(title="Link User to Minecraft IGN", user=user, operation=operation, amount=amount, reason=reason)
            await message.interaction.response.send_modal(modal)
        db.close()

    @manage_group.command()
    async def link(self, message, user: discord.Member, ign):
        db = DB()
        db.connect()
        db.cursor.execute(f'SELECT * FROM discord_links WHERE discord_id = {user.id}')
        rows = db.cursor.fetchall()
        player_uuid = getPlayerUUID(ign)
        if len(rows) != 0:
            db.cursor.execute(f'UPDATE discord_links SET ign = \'{ign}\', uuid = \'{player_uuid[1]}\' WHERE discord_id = {user.id}')
            db.connection.commit()
            db.cursor.execute(f'UPDATE shells SET user = \'{ign}\' WHERE user = \'{rows[0][0]}\'')
            db.connection.commit()
            try:
                current_nick = user.nick.split(' ')
                await user.edit(nick=f'{current_nick[0]} {ign}')
            except:
                pass
        else:
            try:
                current_nick = user.nick.split(' ')
            except:
                current_nick = ['']
            db.cursor.execute(
                f'INSERT INTO discord_links (discord_id, ign, uuid, linked, rank) VALUES ({user.id}, \'{ign}\', \'{player_uuid[0]}\', 0, \'{current_nick[0]}\');')
            db.connection.commit()
        await message.respond(f'Linked **{user.name}** to **{ign}**', ephemeral=True)
        db.close()

    @commands.Cog.listener()
    async def on_ready(self):
        print('Manage commands loaded')


def setup(client):
    client.add_cog(Manage(client))
