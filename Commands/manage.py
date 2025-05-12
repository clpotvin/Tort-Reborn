import os
import time
from datetime import datetime
from io import BytesIO

import discord
from discord import SlashCommandGroup, ApplicationContext
from discord.ext import commands
from discord.ui import Modal, InputText
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests

from Helpers.classes import LinkAccount, PlayerStats, PlayerShells
from Helpers.database import DB
from Helpers.functions import addLine, split_sentence, expand_image, getPlayerUUID
from Helpers.variables import guilds, discord_ranks, discord_rank_roles


class ShellModalName(Modal):
    def __init__(self, user: discord.Member, operation: str, amount: int, reason: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.operation = operation
        self.amount = amount
        self.reason = reason
        self.add_item(
            InputText(
                label="Player's Name", 
                placeholder="Player's In-Game Name without rank"
            )
        )

    async def callback(self, interaction: discord.Interaction):
        db = DB(); db.connect()
        img = Image.new('RGBA', (375, 95), '#100010e2')
        draw = ImageDraw.Draw(img); draw.fontmode = '1'
        font = ImageFont.truetype('images/profile/game.ttf', 19)

        player = PlayerStats(self.children[0].value, 1)
        try:
            url = f"https://visage.surgeplay.com/bust/75/{player.UUID}"
            skin = Image.open(BytesIO(requests.get(url).content))
        except:
            skin = Image.open('images/profile/x-steve.webp')
        img.paste(skin, (10, 10), skin)

        if self.operation == 'add':
            new_amount = player.shells + self.amount
            diff = f'+{self.amount}'
        else:
            new_amount = player.shells - self.amount
            diff = f'-{self.amount}'
        addLine(f'&7All-Time: &f{new_amount} &7({diff}&7)', draw, font, 95, 61)

        db.cursor.execute(
            "INSERT INTO discord_links (discord_id, ign, linked, rank) VALUES (%s, %s, 0, '') ON CONFLICT (discord_id) DO UPDATE SET ign=EXCLUDED.ign;",
            (self.user.id, self.children[0].value)
        )
        db.cursor.execute(
            "INSERT INTO shells (\"user\", shells) VALUES (%s, %s) ON CONFLICT (\"user\") DO UPDATE SET shells=EXCLUDED.shells;",
            (str(self.user.id), new_amount)
        )
        db.connection.commit()

        addLine(f'&f{player.username}', draw, font, 95, 15)
        addLine(f'&7Balance: &f{new_amount} &7({diff}&7)', draw, font, 95, 40)

        if self.reason:
            for line in split_sentence(self.reason):
                img, draw = expand_image(img)
                addLine(f'&3{line}', draw, font, 10, img.height - 25)

        img = ImageOps.expand(img, border=(2,2), fill='#100010e2')
        draw = ImageDraw.Draw(img)
        draw.rectangle((2,2,img.width-3,img.height-3), outline='#240059', width=2)

        buf = BytesIO(); img.save(buf, 'PNG'); buf.seek(0)
        file = discord.File(buf, filename=f"shell_{int(time.time())}.png")
        await interaction.response.send_message(file=file)
        db.close()


class Manage(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

    manage_group = SlashCommandGroup(
        'manage', 'Guild management commands',
        guild_ids=guilds,
        default_member_permissions=discord.Permissions(manage_roles=True)
    )

    @manage_group.command(name='rank', description='Assign or update a user’s guild rank')
    async def rank(
        self,
        ctx: ApplicationContext,
        user: discord.Member,
        rank: discord.Option(str, choices=[
            'Starfish','Manatee','Piranha','Barracuda','Angler',
            'Hammerhead','Sailfish','Dolphin','Narwhal'
        ])
    ):
        db = DB(); db.connect()
        db.cursor.execute(
            "SELECT ign FROM discord_links WHERE discord_id = %s", (user.id,)
        )
        rows = db.cursor.fetchall()
        added = 'Added Roles:'
        removed = 'Removed Roles:'
        all_roles = ctx.guild.roles

        if rows:
            await ctx.defer(ephemeral=True)
            for role_name in discord_ranks[rank]['roles']:
                role_obj = discord.utils.get(all_roles, name=role_name)
                if role_obj and role_obj not in user.roles:
                    await user.add_roles(role_obj)
                    added += f"\n - {role_name}"
            for role_name in [r for r in discord_rank_roles if r not in discord_ranks[rank]['roles']]:
                role_obj = discord.utils.get(all_roles, name=role_name)
                if role_obj and role_obj in user.roles:
                    await user.remove_roles(role_obj)
                    removed += f"\n - {role_name}"
            db.cursor.execute(
                "UPDATE discord_links SET rank = %s WHERE discord_id = %s",
                (rank, user.id)
            )
            db.connection.commit()
            try:
                current = user.nick or user.name
                parts = current.split(' ', 1)
                base = parts[1] if len(parts) > 1 else parts[0]
                await user.edit(nick=f"{rank} {base}")
            except Exception:
                pass
            await ctx.followup.send(f"{added}\n\n{removed}", ephemeral=True)
        else:
            modal = LinkAccount(
                title="Link User to Minecraft IGN",
                user=user,
                rank=rank,
                added=added,
                removed=removed
            )
            await ctx.interaction.response.send_modal(modal)
        db.close()

    @manage_group.command(name='shells', description='Add or remove shells from a user')
    async def shells(
        self,
        ctx: ApplicationContext,
        operation: discord.Option(str, choices=['add','remove']),
        user: discord.Member,
        amount: int,
        # reason: discord.Option(str, required=False, default='')
    ):
        db = DB(); db.connect()
        db.cursor.execute(
            "SELECT ign FROM discord_links WHERE discord_id = %s", (user.id,)
        )
        rows = db.cursor.fetchall()

        if rows:
            await ctx.defer()
            player = PlayerShells(user.id)
            img = Image.new('RGBA', (375,95), '#100010e2')
            draw = ImageDraw.Draw(img); draw.fontmode='1'
            font = ImageFont.truetype('images/profile/game.ttf',19)
            try:
                headers = {'User-Agent': os.getenv("visage_UA")}
                url = f"https://visage.surgeplay.com/bust/75/{player.UUID}"
                skin = Image.open(BytesIO(requests.get(url, headers=headers).content))
            except:
                skin = Image.open('images/profile/X-Steve.webp')
            img.paste(skin,(10,10),skin)
            if operation == 'add':
                new_total = player.shells + amount
                new_bal = player.balance + amount
                diff = f'+{amount}'
                db.cursor.execute(
                    "UPDATE shells SET shells = %s, balance = %s WHERE \"user\" = %s",
                    (new_total, new_bal, str(user.id))
                )
                addLine(f'&7All-Time: &f{new_total} &7({diff}&7)', draw, font, 95, 61)
            else:
                new_bal = player.balance - amount
                diff = f'-{amount}'
                db.cursor.execute(
                    "UPDATE shells SET balance = %s WHERE \"user\" = %s",
                    (new_bal, str(user.id))
                )
                addLine(f'&7All-Time: &f{player.shells}', draw, font, 95, 61)
            addLine(f'&f{player.username}', draw, font, 95, 15)
            addLine(f'&7Balance: &f{new_bal} &7({diff}&7)', draw, font, 95, 40)
            # if reason:
            #     for line in split_sentence(reason):
            #         img, draw = expand_image(img)
            #         addLine(f'&3{line}', draw, font, 10, img.height-25)
            db.connection.commit()
            # Log
            with open('shell.log','a') as f:
                ts = datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
                f.write(f'[{ts}] {ctx.user.name} {operation}ed {amount} to {player.username}.\n')
            img = ImageOps.expand(img,border=(2,2),fill='#100010e2')
            draw = ImageDraw.Draw(img)
            draw.rectangle((2,2,img.width-3,img.height-3),outline='#240059',width=2)
            buf = BytesIO(); img.save(buf,'PNG'); buf.seek(0)
            file = discord.File(buf, filename=f"shells_{int(time.time())}.png")
            await ctx.followup.send(file=file)
        else:
            modal = ShellModalName(
                title="Link User to Minecraft IGN",
                user=user,
                operation=operation,
                amount=amount,
                # set to empty for now
                reason=''
            )
            await ctx.interaction.response.send_modal(modal)
        db.close()

    @manage_group.command(name='link', description='Link a user to an IGN')
    async def link(
        self,
        ctx: ApplicationContext,
        user: discord.Member,
        ign: str
    ):
        db = DB(); db.connect()
        uuid = getPlayerUUID(ign)[1]
        db.cursor.execute(
            "SELECT * FROM discord_links WHERE discord_id = %s", (user.id,)
        )
        if db.cursor.fetchone():
            db.cursor.execute(
                "UPDATE discord_links SET ign = %s, uuid = %s WHERE discord_id = %s",
                (ign, uuid, user.id)
            )
            db.cursor.execute(
                "INSERT INTO shells (\"user\") VALUES (%s) ON CONFLICT DO NOTHING",
                (str(user.id),)
            )
            db.connection.commit()
            try:
                base = user.nick.split(' ')[0]
                await user.edit(nick=f"{base} {ign}")
            except:
                pass
            await ctx.respond(f'Updated link for **{user.name}** to **{ign}**', ephemeral=True)
        else:
            base = (user.nick.split(' ')[0] if user.nick else '')
            db.cursor.execute(
                "INSERT INTO discord_links (discord_id, ign, uuid, linked, rank) VALUES (%s,%s,%s,False,%s)",
                (user.id, ign, uuid, base)
            )
            db.connection.commit()
            await ctx.respond(f'Linked **{user.name}** to **{ign}**', ephemeral=True)
        db.close()

    @commands.Cog.listener()
    async def on_ready(self):
        print('Manage commands loaded')


def setup(client):
    client.add_cog(Manage(client))
