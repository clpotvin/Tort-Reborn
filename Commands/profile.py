import os
import time
from io import BytesIO

import discord
import requests
from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands
from discord.commands import slash_command
import json

from Helpers.classes import PlayerStats
from Helpers.functions import pretty_date, generate_rank_badge, generate_banner, getData, format_number, addLine, vertical_gradient, round_corners, generate_badge
from Helpers.variables import discord_ranks, minecraft_colors, minecraft_banner_colors


class Profile(commands.Cog):
    def __init__(self, client):
        self.client = client

    @slash_command(description='Displays a guild profile of guild member')
    async def profile(self, ctx: discord.ApplicationContext, name: discord.Option(str, required=True), days: discord.Option(int, min=1, max=30, default=7)):
        await ctx.defer()
        player = PlayerStats(name, days)

        if player.error:
            embed = discord.Embed(title=':no_entry: Oops! Something did not go as intended.',
                                  description=f'Could not retrieve information of `{name}`.\nPlease check your spelling or try again later.',
                                  color=0xe33232)
            await ctx.followup.send(embed=embed, ephemeral=True)
            return

        color = '#ffffff'
        basic_text_color = '#ffffff'
        basic_text_drop_shadow = '#3f3f3f'

        custom_bg_fg = True
        custom_bg_fg_color_1 = '#4585db'
        custom_bg_fg_color_2 = '#2f2b73'

        bg = vertical_gradient(main_color=player.tag_color)
        bg = round_corners(bg)
        draw = ImageDraw.Draw(bg)

        if custom_bg_fg:
            bg_fg = vertical_gradient(width=850, height=1130, main_color=custom_bg_fg_color_1, secondary_color=custom_bg_fg_color_2)
        else:
            bg_fg = vertical_gradient(width=850, height=1130, main_color="#222f72")
        bg.paste(bg_fg, (25, 25), bg_fg)

        fg_bg = vertical_gradient(width=818, height=545, main_color=player.tag_color, reverse=True)
        fg_bg = round_corners(fg_bg)
        bg.paste(fg_bg, (41, 100), fg_bg)

        background = Image.open(f"images/profile_backgrounds/{player.background}.png")
        background = round_corners(background, radius=20)
        bg.paste(background, (50, 110), background)

        try:
            headers = {'User-Agent': os.getenv("visage_UA")}
            url = f"https://visage.surgeplay.com/bust/500/{player.UUID}"
            response = requests.get(url, headers=headers)
            skin = Image.open(BytesIO(response.content))
        except Exception as e:
            print(e)
            skin = Image.open('images/profile/x-steve500.png')
        skin.thumbnail((480, 480))
        bg.paste(skin, (200, 156), skin)

        rank = generate_rank_badge(player.tag_display, player.tag_color)
        rank_w, rank_h = rank.size
        bg.paste(rank, (450 - int(rank_w / 2), 96), rank)

        if player.guild:
            guild_font = ImageFont.truetype('images/profile/minecraft_font.ttf', 40)
            _, _, w, h = draw.textbbox((0, 0), player.guild, font=guild_font)
            try:
                guild_banner = getData(player.guild)['banner']
                if guild_banner['base'] in ['BLACK', 'GRAY', 'BROWN']:
                    for layer in guild_banner['layers']:
                        if layer['colour'] not in ['BLACK', 'GRAY', 'BROWN']:
                            guild_colour = layer['colour']
                            break
                        else:
                            guild_colour = "WHITE"
                else:
                    guild_colour = guild_banner['base']
            except:
                guild_colour = "WHITE"

            guild_badge = generate_badge(text=player.guild, base_color='#{:02x}{:02x}{:02x}'.format(*minecraft_banner_colors[guild_colour]), scale=3)
            guild_badge.crop(guild_badge.getbbox())
            bg.paste(guild_badge, (108, 615), guild_badge)

            if player.taq and player.linked:
                guild_rank_badge = generate_badge(text=player.rank.upper(), base_color=discord_ranks[player.rank]['color'], scale=3)
            else:
                guild_rank_badge = generate_badge(text=player.guild_rank.upper(), base_color='#a0aeb0', scale=3)
            guild_rank_badge.crop(guild_rank_badge.getbbox())

            member_for_badge = generate_badge(text=f'{player.in_guild_for.days} D', base_color='#363636', scale=3)
            member_for_badge.crop(member_for_badge.getbbox())

            grb_w = guild_rank_badge.width

            bg.paste(member_for_badge, (90 + grb_w, 667), member_for_badge)
            bg.paste(guild_rank_badge, (108, 667), guild_rank_badge)

            banner = generate_banner(player.guild, 15, "2")
            banner.thumbnail((157, 157))
            bg.paste(banner, (41, 562))

        name_font = ImageFont.truetype('images/profile/game.ttf', 50)
        _, _, w, h = draw.textbbox((0, 0), player.username, font=name_font)
        name_img = Image.new("RGBA", (800, 100), (0, 0, 0, 0))
        name_draw = ImageDraw.Draw(name_img)
        name_draw.text((7, 7), player.username, font=name_font, fill=basic_text_drop_shadow)
        name_draw.text((0, 0), player.username, font=name_font, fill=basic_text_color)
        bg.paste(name_img, (50, 40), name_img)

        box_l = Image.new('RGBA', (400, 75), (0, 0, 0, 0))
        box_r = Image.new('RGBA', (380, 75), (0, 0, 0, 0))
        box_l_draw = ImageDraw.Draw(box_l)
        box_r_draw = ImageDraw.Draw(box_r)
        box_l_draw.rounded_rectangle([(0, 0), (400, 75)], fill=(0, 0, 0, 30), radius=10)
        box_r_draw.rounded_rectangle([(0, 0), (380, 75)], fill=(0, 0, 0, 30), radius=10)

        for row in range(5):
            bg.paste(box_l, (50, 730 + (row * 85)), box_l)
            bg.paste(box_r, (470, 730 + (row * 85)), box_r)

        title_font = ImageFont.truetype('images/profile/5x5.ttf', 40)
        data_font = ImageFont.truetype('images/profile/game.ttf', 35)
        if player.online:
            draw.text((60, 720), 'World', font=title_font, fill='#fad51e')
            draw.text((440, 765), player.server, font=data_font, anchor="ra")
        else:
            draw.text((60, 720), 'Last seen', font=title_font, fill='#fad51e')
            draw.text((440, 765), pretty_date(player.last_joined), font=data_font, anchor="ra")
        draw.text((60, 805), 'Playtime', font=title_font, fill='#fad51e')
        draw.text((440, 850), f'{int(player.playtime)} hrs', font=data_font, anchor="ra")
        draw.text((60, 890), 'Wars', font=title_font, fill='#fad51e')
        draw.text((440, 935), str(player.wars), font=data_font, anchor="ra")

        draw.text((480, 720), 'Total Level', font=title_font, fill='#fad51e')
        draw.text((840, 765), f'{player.total_level}', font=data_font, anchor="ra")

        if player.guild:
            title_font = ImageFont.truetype('images/profile/5x5.ttf', 40)
            data_font = ImageFont.truetype('images/profile/game.ttf', 35)
            draw.text((60, 975), 'Guild XP', font=title_font, fill='#fad51e')
            draw.text((440, 1020), format_number(player.guild_contributed), font=data_font, anchor="ra")
            if player.taq and player.in_guild_for.days >= 1:
                draw.text((60, 1060), 'Guild Raids', font=title_font, fill='#fad51e')
                draw.text((480, 805), f'Playtime / {player.stats_days} D', font=title_font, fill='#fad51e')
                draw.text((480, 890), f'Wars / {player.stats_days} D', font=title_font, fill='#fad51e')
                draw.text((480, 975), f'Guild XP / {player.stats_days} D', font=title_font, fill='#fad51e')
                draw.text((480, 1060), f'Guild Raids / {player.stats_days} D', font=title_font, fill='#fad51e')

                shells_img = Image.open('images/profile/shells.png')
                shells_img.thumbnail((50, 50))
                data_font = ImageFont.truetype('images/profile/game.ttf', 50)
                _, _, w, h = draw.textbbox((0, 0), '{:,}'.format(player.balance), font=data_font)
                bal_img = Image.new("RGBA", (800, 100), (0, 0, 0, 0))
                bal_draw = ImageDraw.Draw(bal_img)
                bal_draw.text((7, 7), str(player.balance), font=data_font, fill=basic_text_drop_shadow)
                bal_draw.text((0, 0), str(player.balance), font=data_font, fill=basic_text_color)
                bg.paste(bal_img, (780 - (30 * len(str(player.balance))), 40), bal_img)
                bg.paste(shells_img, (800, 40), shells_img)

        with BytesIO() as file:
            bg.save(file, format="PNG")
            file.seek(0)
            t = int(time.time())
            profile_card = discord.File(file, filename=f"profile{t}.png")

        await ctx.followup.send(file=profile_card)

        if player.linked:
            if str(ctx.author.id) == player.discord and player.in_guild_for.days >= 365 and 4 not in player.backgrounds_owned:
                embed = discord.Embed(title=':tada: New background unlocked!',
                                      description=f'<@{player.discord}> unlocked the **1 Year Anniversary** background!',
                                      color=0x34eb40)
                bg_file = discord.File(f'./images/profile_backgrounds/4.png', filename=f"4.png")
                embed.set_thumbnail(url=f"attachment://4.png")

                unlock = player.unlock_background('1 Year Anniversary')
                if unlock:
                    await ctx.channel.send(embed=embed, file=bg_file)

            if str(ctx.author.id) == player.discord and player.rank.upper() in ['NARWHAL','HYDRA'] and 3 not in player.backgrounds_owned:
                embed = discord.Embed(title=':tada: New background unlocked!',
                                      description=f'<@{player.discord}> unlocked the **TAq Sea Turtle** background!',
                                      color=0x34eb40)
                bg_file = discord.File(f'./images/profile_backgrounds/3.png', filename=f"3.png")
                embed.set_thumbnail(url=f"attachment://3.png")

                unlock = player.unlock_background('TAq Sea Turtle')
                if unlock:
                    await ctx.channel.send(embed=embed, file=bg_file)

    @commands.Cog.listener()
    async def on_ready(self):
        print('NewProfile command loaded')


def setup(client):
    client.add_cog(Profile(client))
