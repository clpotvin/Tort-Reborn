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
from Helpers.functions import pretty_date, generate_rank_badge, generate_banner, getData, format_number, addLine
from Helpers.variables import discord_ranks, minecraft_colors


class Profile(commands.Cog):
    def __init__(self, client):
        self.client = client

    @slash_command(description='Displays a guild profile of guild member')
    async def profile(self, message, name: discord.Option(str, require=True),
                      days: discord.Option(int, min=1, max=30, default=7)):
        # await message.defer()
        player = PlayerStats(name, days)

        if player.error:
            print
            embed = discord.Embed(title=':no_entry: Oops! Something did not go as intended.',
                                  description=f'Could not retrieve information of `{name}`.\nPlease check your spelling or try again later.',
                                  color=0xe33232)
            await message.followup.send(embed=embed, ephemeral=True)
            return
        if player.guild:
            bg = Image.open('images/profile/bg_taq.png')
        else:
            bg = Image.open('images/profile/bg_guildless.png')
        color = '#ffffff'
        draw = ImageDraw.Draw(bg)

        # background
        background = Image.open(f"images/profile_backgrounds/{player.background}.png")
        bg.paste(background, (0, 0), background)

        # skin
        try:
            headers = {'User-Agent': os.getenv("visage_UA")}
            url = f"https://visage.surgeplay.com/bust/500/{player.UUID}"
            response = requests.get(url, headers=headers)
            skin = Image.open(BytesIO(response.content))
        except Exception as e:
            print(e)
            skin = Image.open('images/profile/x-steve500.png')
        bg.paste(skin, (150, 26), skin)

        rank = generate_rank_badge(player.tag_display, player.tag_color)
        rank_w, rank_h = rank.size
        bg.paste(rank, (400 - int(rank_w / 2), 483 - int(rank_h / 2)), rank)

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
        name_font = ImageFont.truetype('images/profile/minecraft_font.ttf', 64)
        _, _, w, h = draw.textbbox((0, 0), player.username, font=name_font)
        draw.text(((800 - w) / 2, 520), player.username, font=name_font, fill=player.tag_color)

        # profile stats
        title_font = ImageFont.truetype('images/profile/5x5.ttf', 35)
        data_font = ImageFont.truetype('images/profile/minecraft_font.ttf', 42)
        if player.online:
            draw.text((50, 590), 'World', font=title_font, fill='#fad51e')
            draw.text((50, 620), player.server, font=data_font)
        else:
            draw.text((50, 590), 'Last seen', font=title_font, fill='#fad51e')
            draw.text((50, 620), pretty_date(player.last_joined), font=data_font)
        draw.text((450, 590), 'Wars', font=title_font, fill='#fad51e')
        draw.text((450, 620), str(player.wars), font=data_font)
        draw.text((50, 680), 'Playtime', font=title_font, fill='#fad51e')
        draw.text((50, 710), f'{int(player.playtime)} hrs', font=data_font)
        draw.text((450, 680), 'Total Level', font=title_font, fill='#fad51e')
        draw.text((450, 710), f'{player.total_level}', font=data_font)

        if player.guild:
            title_font = ImageFont.truetype('images/profile/5x5.ttf', 35)
            data_font = ImageFont.truetype('images/profile/minecraft_font.ttf', 32)
            draw.text((230, 840), 'Rank', font=title_font, fill='#fad51e')
            if player.taq and player.linked:
                draw.text((230, 872), player.rank.upper(), font=data_font, fill=discord_ranks[player.rank]['color'])
                color = discord_ranks[player.rank]['color']
            else:
                draw.text((230, 872), player.guild_rank.upper(), font=data_font)
            draw.text((230, 915), 'Member for', font=title_font, fill='#fad51e')
            draw.text((230, 947), f'{player.in_guild_for.days} days', font=data_font)
            draw.text((230, 990), 'Guild XP', font=title_font, fill='#fad51e')
            draw.text((230, 1022), format_number(player.guild_contributed), font=data_font)
            if player.taq and player.in_guild_for.days >= 1:
                draw.text((480, 840), f'{player.stats_days}-day Playtime', font=title_font, fill='#fad51e')
                # draw.text((480, 872), f'{player.real_pt} hrs', font=data_font)
                draw.text((480, 915), f'{player.stats_days}-day Wars', font=title_font, fill='#fad51e')
                # draw.text((480, 947), '{:,}'.format(player.real_wars), font=data_font)
                draw.text((480, 990), f'{player.stats_days}-day Guild XP', font=title_font, fill='#fad51e')
                # draw.text((480, 1022), format_number(player.real_xp), font=data_font)

                # shells
                shells_img = Image.open('images/profile/shells.png')
                shells_img.thumbnail((50, 50))
                data_font = ImageFont.truetype('images/profile/minecraft_font.ttf', 42)
                _, _, w, h = draw.textbbox((0, 0), '{:,}'.format(player.balance), font=data_font)
                addLine('&f{:,}'.format(player.balance), draw, data_font, 780 - w, 10)
                bg.paste(shells_img, (718 - w, 13), shells_img)

        # embed
        possessive_noun = '\'s' if player.username[-1] != 's' else '\''
        embed = discord.Embed(title=player.username.replace("_", "\\_") + f'{possessive_noun} playercard',
                              description=f'<:discordlinked:1023567645817188402> <@{player.discord}>' if player.linked else '',
                              color=int(color[1:], 16))
        if player.taq and not player.linked:
            embed.set_footer(
                text='Some information could be more accurate.\nAsk our moderators to link it for you.',
                icon_url='https://media.discordapp.net/attachments/1004096609686143008/1039684902754455612/image.png'
                         '?width=671&height=671')
        with BytesIO() as file:
            bg.save(file, format="PNG")
            file.seek(0)
            t = int(time.time())
            profile_card = discord.File(file, filename=f"profile{t}.png")
            embed.set_image(url=f"attachment://profile{t}.png")

        await message.followup.send(embed=embed, file=profile_card)

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
