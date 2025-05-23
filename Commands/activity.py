import datetime
import time
from io import BytesIO

from PIL import Image, ImageFont, ImageDraw
from dateutil import parser
import discord
from discord.ext import commands
from discord.ext import pages
from discord.commands import slash_command

from Helpers.classes import PlaceTemplate, Page, Guild
from Helpers.database import DB
from Helpers.functions import date_diff, isInCurrDay, getGuildMembers, expand_image, addLine, generate_rank_badge
from Helpers.variables import rank_map
import json
import math

from Helpers.variables import test, guilds



class Activity(commands.Cog):
    def __init__(self, client):
        self.client = client

    @slash_command(description='Displays activity of members')
    async def activity(self, message,
                       order_by: discord.Option(str, choices=['Playtime', 'Inactivity', 'Kick Suitability']),
                       dayss: discord.Option(int, name="days", min_value=1, max_value=30, default=7)):
        if order_by == 'Kick Suitability':
            db = DB()
            db.connect()
        await message.defer()
        book = []
        # new_data = await getGuildActivity(message.channel)
        with open('player_activity.json', 'r') as f:
            old_data = json.loads(f.read())
        with open('current_activity.json', 'r') as f:
            new_data = json.loads(f.read())

        taq = Guild('The Aquarium').all_members
        playerdata = []

        sort_map = {'Playtime': 'playtime',
                    'Inactivity': 'last_join',
                    'Kick Suitability': 'score'}

        title_map = {'Playtime': 'playtime_title.png',
                     'Inactivity': 'inactivity_title.png',
                     'Kick Suitability': 'kick_title.png'
                     }
        bg1 = PlaceTemplate('images/profile/first.png')
        bg2 = PlaceTemplate('images/profile/second.png')
        bg3 = PlaceTemplate('images/profile/third.png')
        bg4 = PlaceTemplate('images/profile/warning.png')
        bg = PlaceTemplate('images/profile/other.png')
        rank_star = Image.open('images/profile/rank_star.png')
        playtime_icon = Image.open('images/profile/playtime.png')
        playtime_icon.thumbnail((16, 16))
        inactive_icon = Image.open('images/profile/inactive.png')
        inactive_icon.thumbnail((16, 16))
        taq_icon = Image.open('images/profile/taq_logo.png')
        taq_icon.thumbnail((16, 16))
        event_icon = Image.open('images/profile/event_team.png')
        event_icon.thumbnail((16, 16))
        gameFont = ImageFont.truetype('images/profile/game.ttf', 19)
        legendFont = ImageFont.truetype('images/profile/5x5.ttf', 20)
        widest = 0

        if order_by == 'Kick Suitability':
            try:
                guild = self.client.get_guild(guilds[0])
            except:
                guild = await self.client.fetch_guild(guilds[0])
            db.cursor.execute(f'SELECT discord_id, ign FROM discord_links')
            rows = db.cursor.fetchall()
            all_roles = guild.roles
            eteam_role = discord.utils.find(lambda r: r.name == 'Event Team', all_roles)

        for member in new_data:
            found = False
            uuid = member['uuid']
            last_join = member['last_join']
            last_seen = date_diff(parser.isoparse(last_join))
            playtime = member['playtime']
            discord_id = False
            eteam = False
            if order_by == 'Kick Suitability':
                for row in rows:
                    if row[1] == member['name']:
                        discord_id = row[0]
                        break
                if discord_id:
                    try:
                        try:
                            discord_member = guild.get_member(int(discord_id))
                        except:
                            discord_member = await guild.fetch_member(discord_id)
                        roles = discord_member.roles
                        if eteam_role in roles:
                            eteam = True
                    except:
                        pass

            for player in taq:
                if player['uuid'] == uuid:
                    joined_date = parser.isoparse(player['joined'])
                    found = True
            day = dayss
            while not isInCurrDay(old_data[day - 1]['members'], uuid) and day - 1 != 0:
                day -= 1
            else:
                for user in old_data[day - 1]['members']:
                    if uuid == user['uuid']:
                        if not found:
                            member_for = datetime.datetime.now() - datetime.datetime.now()
                        else:
                            member_for = datetime.datetime.now() - joined_date.replace(tzinfo=None)
                        real_pt = playtime - user['playtime']
                        break
            activity_score = last_seen * 1.4 - (day * int(real_pt)) * 1.3 - (member_for.days / 20) - (
                    len(rank_map[member['rank'].lower()]) * 1.2)
            if real_pt >= 0:
                if member_for.days < 7 and order_by == "Kick Suitability":
                    pass
                else:
                    playerdata.append(
                        {'name': member['name'], 'uuid': uuid, 'playtime': real_pt, 'last_join': last_seen,
                         'rank': member['rank'], 'eteam': eteam, 'member_for': member_for.days,
                         'score': activity_score})

        if playerdata:
            i = 1
            playerdata.sort(key=lambda x: x[sort_map[order_by]], reverse=True)
        page_num = int(math.ceil(len(playerdata) / 15))
        for page in range(page_num):
            img = Image.new('RGBA', (820, 0), color='#00000000')
            d = ImageDraw.Draw(img)
            d.fontmode = '1'
            page_playerdata = playerdata[(15 * page):15 + (15 * page)]
            for p, player in enumerate(page_playerdata):
                img, d = expand_image(img, border=(0, 0, 0, 36), fill='#00000000')
                hr_playtime = int(player['playtime'])
                if order_by == 'Kick Suitability':
                    if player['score'] >= -1:
                        bg_color = bg4
                        if player['eteam']:
                            img.paste(event_icon, (802, p * 36 + 11), event_icon)
                    else:
                        bg_color = bg
                elif order_by == 'Playtime':
                    match i:
                        case 1:
                            bg_color = bg1
                        case 2:
                            bg_color = bg2
                        case 3:
                            bg_color = bg3
                        case _:
                            bg_color = bg
                else:
                    bg_color = bg
                bg_color.add(img, 800, (0, p * 36 + 3))
                pos = f'{i}.'
                addLine(f'&f{pos}', d, gameFont, 10, p * 36 + 9)
                img.paste(bg_color.divider, (55, p * 36 + 3), bg_color.divider)

                for s in range(len(rank_map[player['rank'].lower()])):
                    img.paste(rank_star, (65 + (s*12), p * 36 + 14), rank_star)

                img.paste(bg_color.divider, (133, p * 36 + 3), bg_color.divider)
                addLine(f'&f{player["name"]}', d, gameFont, 143, p * 36 + 9)
                img.paste(bg_color.divider, (380, p * 36 + 3), bg_color.divider)
                img.paste(playtime_icon, (390, p * 36 + 11), playtime_icon)
                addLine(f'&f{str(hr_playtime) + (" hrs" if hr_playtime != 1 else " hr")}', d, gameFont, 416, p * 36 + 9)
                img.paste(bg_color.divider, (510, p * 36 + 3), bg_color.divider)
                img.paste(inactive_icon, (520, p * 36 + 11), inactive_icon)
                addLine(f'&f{str(player["last_join"]) + (" days" if player["last_join"] != 1 else " day")}', d,
                        gameFont, 546, p * 36 + 9)
                img.paste(bg_color.divider, (640, p * 36 + 3), bg_color.divider)
                img.paste(taq_icon, (650, p * 36 + 11), taq_icon)
                addLine(f'&f{str(player["member_for"]) + (" days" if player["member_for"] != 1 else " day")}', d,
                        gameFont, 676, p * 36 + 9)
                i += 1

            img, d = expand_image(img, border=(0, 120, 0, 20), fill='#00000000')
            title = Image.open(f'images/profile/{title_map[order_by]}')
            img.paste(title, (int(img.width / 2) - int(title.width / 2), 10), title)
            badge = generate_rank_badge(f"{dayss} days", "#0477c9", scale=1)
            img.paste(badge, (int(img.width / 2) - int(badge.width / 2), 98), badge)

            img.paste(playtime_icon, (10, img.height - 18), playtime_icon)
            d.text((36, img.height - 23), "Playtime", font=legendFont)
            img.paste(inactive_icon, (160, img.height - 18), inactive_icon)
            d.text((186, img.height - 23), "Inactivity", font=legendFont)
            img.paste(taq_icon, (330, img.height - 18), taq_icon)
            d.text((356, img.height - 23), "Member for", font=legendFont)

            background = Image.new('RGBA', (img.width, img.height), color='#00000000')
            bg_img = Image.open('images/profile/leaderboard_bg.png')
            background.paste(bg_img,
                             (int(img.width / 2) - int(bg_img.width / 2), int(img.height / 2) - int(bg_img.height / 2)))
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
        await final_book.respond(message.interaction)
        if order_by == 'Kick Suitability':
            db.close()

    @commands.Cog.listener()
    async def on_ready(self):
        print('Activity command loaded')


def setup(client):
    client.add_cog(Activity(client))
