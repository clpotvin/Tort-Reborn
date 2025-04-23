import json
import time
from io import BytesIO

import requests
from PIL import Image, ImageFont, ImageDraw
from flask import Flask, request, send_file

from Helpers.classes import PlayerStats
from Helpers.database import DB
from Helpers.functions import pretty_date, generate_rank_badge
from Helpers.variables import main_guild, discord_ranks

app = Flask(__name__)


@app.route('/card/<path:name>', methods=['GET'])
def card(name):
    if request.method == 'GET':
        try:
            player = PlayerStats(name, 7)
        except:
            print("error")
            return
        bg = Image.open('../images/profile/bg.png')
        color = '#ffffff'
        draw = ImageDraw.Draw(bg)

        # background
        profile_pictures = json.load(open('../backgrounds.json', 'r'))
        if player.UUID in profile_pictures:
            background = Image.open(f"images/profile_pictures/{profile_pictures[player.UUID]}")
            bg.paste(background, (0, 0), background)

        # skin
        url = f"https://visage.surgeplay.com/bust/500/{player.UUID}"
        response = requests.get(url)
        skin = Image.open(BytesIO(response.content))
        bg.paste(skin, (150, 26), skin)

        # guild and rank
        if player.guild:
            guild_font = ImageFont.truetype('images/profile/minecraft_font.ttf', 32)
            if player.linked and player.taq:
                color = discord_ranks[player.rank]["color"]
                rank = generate_rank_badge(player.rank, color)
            else:
                rank = Image.open(f'images/profile/{player.guild_rank}.png')
            rank_w, rank_h = rank.size
            bg.paste(rank, (400 - int(rank_w / 2), 526 - int(rank_h / 2)), rank)
            _, _, w, h = draw.textbbox((0, 0), player.guild, font=guild_font)
            try:
                url = f'https://wynn-guild-banner.toki317.dev/banners/{player.guild}'
                response = requests.get(url)
                banner = Image.open(BytesIO(response.content))
                banner.thumbnail((100, 48))
                bg.paste(banner, (int((800 - w - 30) / 2), 435))
            except:
                pass
            draw.text(((800 - w + 39) / 2, 444), player.guild, font=guild_font, fill='#1c1b1b')
            draw.text(((800 - w + 30) / 2, 440), player.guild, font=guild_font)

        # name
        name_font = ImageFont.truetype('images/profile/minecraft_font.ttf', 64)
        _, _, w, h = draw.textbbox((0, 0), player.username, font=name_font)
        draw.text(((800 - w) / 2, 560), player.username, font=name_font, fill=color)
        draw.text(((800 - w) / 2, 560), player.username, font=name_font, fill=color)

        # profile stats
        title_font = ImageFont.truetype('images/profile/5x5.ttf', 35)
        data_font = ImageFont.truetype('images/profile/minecraft_font.ttf', 42)
        if player.online:
            draw.text((50, 630), 'World', font=title_font, fill='#fad51e')
            draw.text((50, 660), player.server, font=data_font)
        else:
            draw.text((50, 630), 'Last seen', font=title_font, fill='#fad51e')
            draw.text((50, 660), pretty_date(player.last_joined), font=data_font)
        draw.text((50, 720), 'Rank', font=title_font, fill='#fad51e')
        draw.text((50, 750), player.tag, font=data_font, fill=player.tag_color)
        draw.text((50, 810), 'Playtime', font=title_font, fill='#fad51e')
        draw.text((50, 840), f'{player.playtime} hrs', font=data_font)
        draw.text((50, 900), 'Total Level', font=title_font, fill='#fad51e')
        draw.text((50, 930), f'{player.total_level}', font=data_font)

        if player.guild:
            vertical_divider = Image.open('../images/profile/vertical_divider.png')
            bg.paste(vertical_divider, (398, 649), vertical_divider)
            title_font = ImageFont.truetype('images/profile/5x5.ttf', 35)
            data_font = ImageFont.truetype('images/profile/minecraft_font.ttf', 32)
            draw.text((450, 630), 'Guild member for', font=title_font, fill='#fad51e')
            draw.text((450, 662), f'{player.in_guild_for.days} days', font=data_font)
            draw.text((450, 700), 'XP Contribution', font=title_font, fill='#fad51e')
            draw.text((450, 732), '{:,}'.format(player.guild_contributed), font=data_font)
            if player.taq and player.in_guild_for.days >= 1:
                horizontal_divider = Image.open('../images/profile/horizontal_divider.png')
                bg.paste(horizontal_divider, (420, 786), horizontal_divider)
                draw.text((450, 790), f'{player.stats_days}-day stats', font=title_font, fill='#fad51e')
                draw.text((450, 830), f'Playtime', font=title_font, fill='#fad51e')
                draw.text((450, 862), f'{player.real_pt} hrs', font=data_font)
                draw.text((450, 900), f'XP Contribution', font=title_font, fill='#fad51e')
                draw.text((450, 932), '{:,}'.format(player.real_xp), font=data_font)

                # shells
                shells_img = Image.open('../images/profile/shells.png')
                shells_img.thumbnail((50, 50))
                data_font = ImageFont.truetype('images/profile/minecraft_font.ttf', 42)
                _, _, w, h = draw.textbbox((0, 0), '{:,}'.format(player.shells), font=name_font)
                draw.text((780 - w, 10), '{:,}'.format(player.shells), font=data_font)
                bg.paste(shells_img, (718 - w, 13), shells_img)
                bg.thumbnail((320,400))

        # embed
        possessive_noun = '\'s' if player.username[-1] != 's' else '\''

        file = BytesIO()
        bg.save(file, format="PNG")
        file.seek(0)
        return send_file(file, mimetype='image/png')


app.run(host='0.0.0.0', port=8001)
