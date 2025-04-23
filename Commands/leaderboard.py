import json
import math
import time
from io import BytesIO

import discord
from PIL import Image, ImageFont, ImageDraw
from discord import SlashCommandGroup
from discord.ext import commands, pages

from Helpers.classes import PlaceTemplate, Page
from Helpers.database import DB
from Helpers.functions import addLine, expand_image, generate_rank_badge, isInCurrDay
from Helpers.variables import rank_map


def create_leaderboard(order_key, key_icon, header, days=7):
    book = []
    with open('activity2.json', 'r') as f:
        old_data = json.loads(f.read())
    with open('current_activity.json', 'r') as f:
        new_data = json.loads(f.read())
    if days > len(old_data):
        days = len(old_data)
    bg1 = PlaceTemplate('images/profile/first.png')
    bg2 = PlaceTemplate('images/profile/second.png')
    bg3 = PlaceTemplate('images/profile/third.png')
    bg = PlaceTemplate('images/profile/other.png')
    warning_icon = Image.open('images/profile/time_warning.png')
    rank_star = Image.open('images/profile/rank_star.png')
    warning_icon.thumbnail((16, 16))
    icon = Image.open(key_icon)
    icon.thumbnail((16, 16))
    gameFont = ImageFont.truetype('images/profile/game.ttf', 19)
    widest = 0
    playerdata = []
    if order_key == 'shells':
        db = DB()
        db.connect()
    for member in new_data:
        uuid = member['uuid']
        if order_key == 'shells':
            db.cursor.execute(
                f'SELECT discord_links.ign, COALESCE(shells.shells, 0) AS shells FROM discord_links LEFT JOIN shells ON discord_links.discord_id = shells.user WHERE discord_links.uuid = \'{uuid}\';')
            row = db.cursor.fetchone()
            if row:
                cont = row[1]
            else:
                cont = 0
        else:
            cont = member[order_key]
        day = days
        if days > 0:
            while not isInCurrDay(old_data[day - 1]['members'], uuid) and day - 1 != 0:
                day -= 1
            else:
                for user in old_data[day - 1]['members']:
                    if uuid == user['uuid']:
                        real_cont = cont - user[order_key]
                        if day != days:
                            playerdata.append(
                                {'name': member['name'], 'uuid': uuid, 'contributed': real_cont, 'rank': member['rank'],
                                 'warning': True})
                        else:
                            playerdata.append(
                                {'name': member['name'], 'uuid': uuid, 'contributed': real_cont, 'rank': member['rank'],
                                 'warning': False})
        else:
            playerdata.append(
                {'name': member['name'], 'uuid': uuid, 'contributed': cont, 'rank': member['rank'],
                 'warning': False})
    if order_key == 'shells':
        db.close()
    if playerdata:
        i = 1
        playerdata.sort(key=lambda x: x['contributed'], reverse=True)
        page_num = int(math.ceil(len(playerdata) / 10))
        for page in range(page_num):
            img = Image.new('RGBA', (560, 0), color='#00000000')
            d = ImageDraw.Draw(img)
            d.fontmode = '1'
            page_playerdata = playerdata[(10 * page):10 + (10 * page)]
            for p, player in enumerate(page_playerdata):
                img, d = expand_image(img, border=(0, 0, 0, 36), fill='#00000000')
                match i:
                    case 1:
                        bg_color = bg1
                    case 2:
                        bg_color = bg2
                    case 3:
                        bg_color = bg3
                    case _:
                        bg_color = bg
                if player['warning']:
                    img.paste(warning_icon, (img.width - 24, p * 36 + 11), warning_icon)
                bg_color.add(img, 530, (0, p * 36 + 3))
                img.paste(bg_color.divider, (55, p * 36 + 3), bg_color.divider)
                pos = f'{i}.'
                addLine(f'&f{pos}', d, gameFont, 10, p * 36 + 9)

                for s in range(len(rank_map[player['rank'].lower()])):
                    img.paste(rank_star, (65 + (s * 12), p * 36 + 14), rank_star)

                img.paste(bg_color.divider, (133, p * 36 + 3), bg_color.divider)
                addLine(f'&f{player["name"]}', d, gameFont, 143, p * 36 + 9)
                _, _, w, h = d.textbbox((0, 0), "{:,}".format(int(player["contributed"])), font=gameFont)
                if i == 1:
                    widest = w
                addLine(f'&f{"{:,}".format(int(player["contributed"]))}', d, gameFont, img.width - 40 - w, p * 36 + 9)
                img.paste(icon, (img.width - 65 - widest, p * 36 + 11), icon)
                img.paste(bg_color.divider, (img.width - 75 - widest, p * 36 + 3), bg_color.divider)
                i += 1

            img, d = expand_image(img, border=(0, 120, 0, 20), fill='#00000000')
            title = Image.open(header)
            img.paste(title, (int(img.width / 2) - int(title.width / 2), 10), title)
            if days > 0:
                badge = generate_rank_badge(f"{days} days", "#0477c9", scale=1)
            else:
                badge = generate_rank_badge(f"All-Time", "#0477c9", scale=1)
            img.paste(badge, (int(img.width / 2) - int(badge.width / 2), 98), badge)

            background = Image.new('RGBA', (img.width, img.height), color='#00000000')
            bg_img = Image.open('images/profile/leaderboard_bg.png')
            background.paste(bg_img,
                             (int(img.width / 2) - int(bg_img.width / 2),
                              int(img.height / 2) - int(bg_img.height / 2)))
            background.paste(img, (0, 0), img)

            with BytesIO() as file:
                background.save(file, format="PNG")
                file.seek(0)
                t = int(time.time())
                leaderboard_img = discord.File(file, filename=f"leaderboard{t}_{page}.png")
            book.append(Page(content='', files=[leaderboard_img]))

        final_book = pages.Paginator(pages=book)
        final_book.add_button(
            pages.PaginatorButton("prev", emoji="<:left_arrow:1198703157501509682>", style=discord.ButtonStyle.red))
        final_book.add_button(
            pages.PaginatorButton("next", emoji="<:right_arrow:1198703156088021112>", style=discord.ButtonStyle.green))
        final_book.add_button(pages.PaginatorButton("first", emoji="<:first_arrows:1198703152204103760>",
                                                    style=discord.ButtonStyle.blurple))
        final_book.add_button(pages.PaginatorButton("last", emoji="<:last_arrows:1198703153726627880>",
                                                    style=discord.ButtonStyle.blurple))
    return final_book


class Leaderboard(commands.Cog):
    def __init__(self, client):
        self.client = client

    leaderboard_group = SlashCommandGroup('leaderboard', 'Leaderboard commands')

    @leaderboard_group.command()
    async def xp(self, message, period: discord.Option(str, choices=['All-Time', '7 Days', '14 Days',
                                                                     '30 Days', 'Custom']),
                 days: discord.Option(int, min_value=1, max_value=30, default=7)):
        await message.defer()

        match period:
            case 'All-Time':
                days = -1
            case '7 Days':
                days = 7
            case '14 Days':
                days = 14
            case '30 Days':
                days = 30

        background_book = create_leaderboard('contributed', 'images/profile/xp.png', 'images/profile/guxp_title.png',
                                             days=days)

        await background_book.respond(message.interaction)

    @leaderboard_group.command()
    async def wars(self, message, period: discord.Option(str, choices=['All-Time', '7 Days', '14 Days',
                                                                       '30 Days', 'Custom']),
                   days: discord.Option(int, min_value=1, max_value=30, default=7)):
        await message.defer()

        match period:
            case 'All-Time':
                days = -1
            case '7 Days':
                days = 7
            case '14 Days':
                days = 14
            case '30 Days':
                days = 30

        background_book = create_leaderboard('wars', 'images/profile/wars.png', 'images/profile/wars_title.png',
                                             days=days)

        await background_book.respond(message.interaction)

    @leaderboard_group.command()
    async def playtime(self, message, period: discord.Option(str, choices=['All-Time', '7 Days', '14 Days',
                                                                           '30 Days', 'Custom']),
                       days: discord.Option(int, min_value=1, max_value=30, default=7)):
        await message.defer()

        match period:
            case 'All-Time':
                days = -1
            case '7 Days':
                days = 7
            case '14 Days':
                days = 14
            case '30 Days':
                days = 30

        background_book = create_leaderboard('playtime', 'images/profile/playtime.png',
                                             'images/profile/playtime_title.png', days=days)

        await background_book.respond(message.interaction)

    @leaderboard_group.command()
    async def shells(self, message, period: discord.Option(str, choices=['All-Time', '7 Days', '14 Days',
                                                                         '30 Days', 'Custom']),
                     days: discord.Option(int, min_value=1, max_value=30, default=7)):
        await message.defer()

        match period:
            case 'All-Time':
                days = -1
            case '7 Days':
                days = 7
            case '14 Days':
                days = 14
            case '30 Days':
                days = 30

        background_book = create_leaderboard('shells', 'images/profile/shells.png',
                                             'images/profile/shell_leaderboard.png', days=days)

        await background_book.respond(message.interaction)

    @commands.Cog.listener()
    async def on_ready(self):
        print('Leaderboard commands loaded')


def setup(client):
    client.add_cog(Leaderboard(client))
