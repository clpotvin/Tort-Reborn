import os
from dotenv import load_dotenv

load_dotenv()
test = os.getenv("TEST_MODE").lower() in ('true', '1', 't')

unknown_channel_redirect = 1367285315236008036

if test:
    guilds = [1364751619018850405, 1369134564450107412]
    te = 1364751619018850405
    changelog_channel = 1367276640207507617
    guildbank_channel = unknown_channel_redirect
    log_channel = unknown_channel_redirect
    attention_channel = unknown_channel_redirect
    eco_learning_channel = unknown_channel_redirect
    rank_up_channel = unknown_channel_redirect
    promotion_channel = unknown_channel_redirect
else:
    guilds = [729147655875199017, 1364751619018850405]
    te = 784795827808763904
    changelog_channel = 1367276640207507617
    guildbank_channel = None
    log_channel = None
    attention_channel = None
    eco_learning_channel = None
    rank_up_channel = None
    promotion_channel = None

golden_tort = [644071980160647178, 419845975000219648, 282914836084686848]

banned_words = []

rank_map = {'recruit': '', 'recruiter': '*', 'captain': '**', 'strategist': '***', 'chief': '****', 'owner': '*****'}
class_map = {'archer': '<:bow:966079566189842482>', 'hunter': '<:bow2:966079565791363162>',
             'assassin': '<:dagger:966079565770416138>', 'ninja': '<:dagger2:966079565770424400>',
             'shaman': '<:relik:966079565833326602>', 'skyseer': '<:relik2:966079565757820978>',
             'warrior': '<:spear:966079565782986852>', 'knight': '<:spear2:966079565703282799>',
             'mage': '<:wand:966079565564887062>', 'darkwizard': '<:wand2:966079565795573780>'}


discord_rank_roles = ['Starfish', '☆Reef', 'Manatee', '★Coastal Waters', 'Piranha', 'Barracuda', '★★ Azure Ocean',
                      'Angler', '★☆☆ Blue Sea',
                      'Hammerhead', '★★☆Deep Sea', 'Sailfish', '★★★Dark Sea', 'Dolphin', 'Trial-Narwhal', 'Narwhal',
                      '★★★★Abyss Waters', '🛡️MODERATOR⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀', '🛡️SR. MODERATOR⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀', '✫✪✫ Hydra - Leader']

discord_ranks = {
    'Starfish': {
        'in_game_rank': 'RECRUIT',
        'stars': '',
        'color': '#e8a41c',
        'image': 'starfish',
        'roles': ['Starfish', '☆Reef']
    },
    'Manatee': {
        'in_game_rank': 'RECRUITER',
        'stars': '*',
        'color': '#ffe226',
        'image': 'manatee',
        'roles': ['Manatee', '★Coastal Waters']
    },
    'Piranha': {
        'in_game_rank': 'CAPTAIN',
        'stars': '**',
        'color': '#c8ff00',
        'image': 'piranha',
        'roles': ['Piranha', '★★ Azure Ocean']
    },
    'Barracuda': {
        'in_game_rank': 'CAPTAIN',
        'stars': '**',
        'color': '#79e64a',
        'image': 'barracuda',
        'roles': ['Barracuda', '★★ Azure Ocean']
    },
    'Angler': {
        'in_game_rank': 'STRATEGIST',
        'stars': '***',
        'color': '#00e2db',
        'image': 'angler',
        'roles': ['Angler', '★☆☆ Blue Sea']
    },
    'Hammerhead': {
        'in_game_rank': 'STRATEGIST',
        'stars': '***',
        'color': '#04b0eb',
        'image': 'hammerhead',
        'roles': ['Hammerhead', '★★☆Deep Sea', '🛡️MODERATOR⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀']
    },
    'Sailfish': {
        'in_game_rank': 'STRATEGIST',
        'stars': '***',
        'color': '#396aff',
        'image': 'sailfish',
        'roles': ['Sailfish', '★★★Dark Sea', '🛡️MODERATOR⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀']
    },
    'Dolphin': {
        'in_game_rank': 'CHIEF',
        'stars': '****',
        'color': '#9d68ff',
        'image': 'dolphin',
        'roles': ['Dolphin', '★★★Dark Sea', '🛡️MODERATOR⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀']
    },
    'Narwhal': {
        'in_game_rank': 'CHIEF',
        'stars': '****',
        'color': '#eb2279',
        'image': 'narwhal',
        'roles': ['Narwhal', '★★★★Abyss Waters', '🛡️MODERATOR⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀', '🛡️SR. MODERATOR⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀']
    },
    'Hydra': {
        'in_game_rank': 'OWNER',
        'stars': '*****',
        'color': '#ac034c',
        'image': 'hydra',
        'roles': ['✫✪✫ Hydra - Leader', '🛡️MODERATOR⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀', '🛡️SR. MODERATOR⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀']
    }
}

minecraft_colors = {"BLACK": (25, 25, 25),
              "GRAY": (76, 76, 76),
              "SILVER": (153, 153, 153),
              "WHITE": (255, 255, 255),
              "PINK": (242, 127, 165),
              "MAGENTA": (178, 76, 216),
              "PURPLE": (127, 63, 178),
              "BLUE": (51, 76, 178),
              "CYAN": (76, 127, 153),
              "LIGHT_BLUE": (102, 153, 216),
              "GREEN": (102, 127, 51),
              "LIME": (127, 204, 25),
              "YELLOW": (229, 229, 51),
              "ORANGE": (216, 127, 51),
              "BROWN": (102, 76, 51),
              "RED": (153, 51, 51)}

colours = {"0": '#000000',
           "1": '#0000AA',
           "2": '#00AA00',
           "3": '#00AAAA',
           "4": '#AA0000',
           "5": '#AA00AA',
           "6": '#FFAA00',
           "7": '#AAAAAA',
           "8": '#555555',
           "9": '#5555FF',
           "a": '#55FF55',
           "b": '#55FFFF',
           "c": '#FF5555',
           "d": '#FF55FF',
           "e": '#FFFF55',
           "f": '#FFFFFF'}

shadows = {"0": '#000000',
           "1": '#00002A',
           "2": '#002A00',
           "3": '#002A2A',
           "4": '#2A0000',
           "5": '#2A002A',
           "6": '#2A2A00',
           "7": '#2A2A2A',
           "8": '#151515',
           "9": '#15153F',
           "a": '#153F15',
           "b": '#153F3F',
           "c": '#3F1515',
           "d": '#3F153F',
           "e": '#3F3F15',
           "f": '#3F3F3F'}

wynn_ranks = {
    "champion": {"color": "#ffa214", "display": "CHAMPION"},
    "hero": {"color": "#8b3f8c", "display": "HERO"},
    "vipplus": {"color": "#5a7dbf", "display": "VIP+"},
    "vip": {"color": "#44aa33", "display": "VIP"},
    "media": {"color": "#bf3399", "display": "MEDIA"},
    "admin": {"color": "#d11111", "display": "ADMIN"},
    "administrator": {"color": "#d11111", "display": "ADMIN"},
    "dev": {"color": "#d11111", "display": "DEVELOPER"},
    "web": {"color": "#d11111", "display": "WEB"},
    "owner": {"color": "#aa0000", "display": "OWNER"},
    "moderator": {"color": "#ff6a00", "display": "MODERATOR"},
    "artist": {"color": "#00aaaa", "display": "ARTIST"},
    "builder": {"color": "#00aaaa", "display": "BUILDER"},
    "cmd": {"color": "#00aaaa", "display": "CMD"},
    "gm": {"color": "#00aaaa", "display": "GM"},
    "hybrid": {"color": "#00aaaa", "display": "HYBRID"},
    "item": {"color": "#00aaaa", "display": "ITEM"},
    "music": {"color": "#00aaaa", "display": "MUSIC"},
    "qa": {"color": "#00aaaa", "display": "QA"}
}
