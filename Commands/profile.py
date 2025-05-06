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
from Helpers.functions import pretty_date, generate_rank_badge, generate_banner, getData, format_number, addLine, vertical_gradient, round_corners
from Helpers.variables import discord_ranks, minecraft_colors


class Profile(commands.Cog):
    def __init__(self, client):
        self.client = client

    @slash_command(description='Displays a guild profile of guild member')
    async def profile(self, message, name: discord.Option(str, require=True),
                      days: discord.Option(int, min=1, max=30, default=7)):
        await message.defer()
        player = PlayerStats(name, days)

        if player.error:
            print
            embed = discord.Embed(title=':no_entry: Oops! Something did not go as intended.',
                                  description=f'Could not retrieve information of `{name}`.\nPlease check your spelling or try again later.',
                                  color=0xe33232)
            await message.followup.send(embed=embed, ephemeral=True)
            return

        bg = vertical_gradient(colour=player.tag_color)
        bg = round_corners(bg)
        color = '#ffffff'
        text_color = '#ffffff'
        text_drop_shadow = '#3f3f3f'
        draw = ImageDraw.Draw(bg)

        bg_fg = vertical_gradient(width=850, height=1130, colour="#222f72")
        bg.paste(bg_fg, (25, 25), bg_fg)

        fg_bg = vertical_gradient(width=820, height=545, colour=player.tag_color, reverse=True)
        fg_bg = round_corners(fg_bg)
        bg.paste(fg_bg, (40, 100), fg_bg)

        # background
        background = Image.open(f"images/profile_backgrounds/{player.background}.png")
        background = round_corners(background)
        bg.paste(background, (50, 110), background)

        # skin
        try:
            headers = {'User-Agent': os.getenv("visage_UA")}
            url = f"https://visage.surgeplay.com/bust/500/{player.UUID}"
            response = requests.get(url, headers=headers)
            skin = Image.open(BytesIO(response.content))
        except Exception as e:
            print(e)
            skin = Image.open('images/profile/x-steve500.png')
        bg.paste(skin, (150+50, 26+110), skin)

        rank = generate_rank_badge(player.tag_display, player.tag_color)
        rank_w, rank_h = rank.size
        bg.paste(rank, (400 - int(rank_w / 2)+50, 483 - int(rank_h / 2)+110), rank)

        # guild and rank
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
            draw.text((230, 790), player.guild, font=guild_font, fill=minecraft_colors[guild_colour])

            banner = generate_banner(player.guild, 15, "2")
            banner.thumbnail((260, 260))
            bg.paste(banner, (50, 800))

        # name
        name_font = ImageFont.truetype('images/profile/game.ttf', 50)
        _, _, w, h = draw.textbbox((0, 0), player.username, font=name_font)
        name_img = Image.new("RGBA", (800, 100), (0, 0, 0, 0))
        name_draw = ImageDraw.Draw(name_img)
        name_draw.text((7, 7), player.username, font=name_font, fill=text_drop_shadow)
        name_draw.text((0, 0), player.username, font=name_font, fill=text_color)
        bg.paste(name_img, (50, 40), name_img)

        # profile stats
        title_font = ImageFont.truetype('images/profile/5x5.ttf', 35)
        data_font = ImageFont.truetype('images/profile/minecraft_font.ttf', 42)
        if player.online:
            draw.text((50+50, 590+110), 'World', font=title_font, fill='#fad51e')
            draw.text((50+50, 620+110), player.server, font=data_font)
        else:
            draw.text((50+50, 590+110), 'Last seen', font=title_font, fill='#fad51e')
            draw.text((50+50, 620+110), pretty_date(player.last_joined), font=data_font)
        draw.text((450+50, 590+110), 'Wars', font=title_font, fill='#fad51e')
        draw.text((450+50, 620+110), str(player.wars), font=data_font)
        draw.text((50+50, 680+110), 'Playtime', font=title_font, fill='#fad51e')
        draw.text((50+50, 710+110), f'{int(player.playtime)} hrs', font=data_font)
        draw.text((450+50, 680+110), 'Total Level', font=title_font, fill='#fad51e')
        draw.text((450+50, 710+110), f'{player.total_level}', font=data_font)

        if player.guild:
            title_font = ImageFont.truetype('images/profile/5x5.ttf', 35)
            data_font = ImageFont.truetype('images/profile/minecraft_font.ttf', 32)
            draw.text((230+50, 840+110), 'Rank', font=title_font, fill='#fad51e')
            if player.taq and player.linked:
                draw.text((230+50, 872+110), player.rank.upper(), font=data_font, fill=discord_ranks[player.rank]['color'])
                color = discord_ranks[player.rank]['color']
            else:
                draw.text((230+50, 872+110), player.guild_rank.upper(), font=data_font)
            draw.text((230+50, 915+110), 'Member for', font=title_font, fill='#fad51e')
            draw.text((230+50, 947+110), f'{player.in_guild_for.days} days', font=data_font)
            draw.text((230+50, 990+110), 'Guild XP', font=title_font, fill='#fad51e')
            draw.text((230+50, 1022+110), format_number(player.guild_contributed), font=data_font)
            if player.taq and player.in_guild_for.days >= 1:
                draw.text((480+50, 840+110), f'{player.stats_days}-day Playtime', font=title_font, fill='#fad51e')
                # draw.text((480, 872), f'{player.real_pt} hrs', font=data_font)
                draw.text((480+50, 915+110), f'{player.stats_days}-day Wars', font=title_font, fill='#fad51e')
                # draw.text((480, 947), '{:,}'.format(player.real_wars), font=data_font)
                draw.text((480+50, 990+110), f'{player.stats_days}-day Guild XP', font=title_font, fill='#fad51e')
                # draw.text((480, 1022), format_number(player.real_xp), font=data_font)

                # shells
                shells_img = Image.open('images/profile/shells.png')
                shells_img.thumbnail((50, 50))
                data_font = ImageFont.truetype('images/profile/game.ttf', 50)
                _, _, w, h = draw.textbbox((0, 0), '{:,}'.format(player.balance), font=data_font)
                bal_img = Image.new("RGBA", (800, 100), (0, 0, 0, 0))
                bal_draw = ImageDraw.Draw(bal_img)
                bal_draw.text((7, 7), str(player.balance), font=data_font, fill=text_drop_shadow)
                bal_draw.text((0, 0), str(player.balance), font=data_font, fill=text_color)
                bg.paste(bal_img, (780 - (30 * len(str(player.balance))), 40), bal_img)
                # addLine('&f{:,}'.format(player.balance), draw, data_font, 780 - w, 40)
                bg.paste(shells_img, (800, 38), shells_img)

        # embed
        possessive_noun = '\'s' if player.username[-1] != 's' else '\''
        with BytesIO() as file:
            bg.save(file, format="PNG")
            file.seek(0)
            t = int(time.time())
            profile_card = discord.File(file, filename=f"profile{t}.png")

        await message.followup.send(file=profile_card)

        if player.linked:
            # 1 Year background unlock
            if str(message.author.id) == player.discord and player.in_guild_for.days >= 365 and 4 not in player.backgrounds_owned:
                embed = discord.Embed(title=':tada: New background unlocked!',
                                      description=f'<@{player.discord}> unlocked the **1 Year Anniversary** background!',
                                      color=0x34eb40)
                bg_file = discord.File(f'./images/profile_backgrounds/4.png', filename=f"4.png")
                embed.set_thumbnail(url=f"attachment://4.png")

                unlock = player.unlock_background('1 Year Anniversary')
                if unlock:
                    await message.channel.send(embed=embed, file=bg_file)

            # Narwhal background unlock
            if str(message.author.id) == player.discord and player.rank.upper() in ['NARWHAL','HYDRA'] and 3 not in player.backgrounds_owned:
                embed = discord.Embed(title=':tada: New background unlocked!',
                                      description=f'<@{player.discord}> unlocked the **TAq Sea Turtle** background!',
                                      color=0x34eb40)
                bg_file = discord.File(f'./images/profile_backgrounds/3.png', filename=f"3.png")
                embed.set_thumbnail(url=f"attachment://3.png")

                unlock = player.unlock_background('TAq Sea Turtle')
                if unlock:
                    await message.channel.send(embed=embed, file=bg_file)




    @commands.Cog.listener()
    async def on_ready(self):
        print('NewProfile command loaded')


def setup(client):
    client.add_cog(Profile(client))
