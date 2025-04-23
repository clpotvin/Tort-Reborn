from requests import get
from dateutil import parser
from datetime import datetime
from time import sleep
from json import dump, load


with open('online_players.json', 'r') as f:
    players_data = load(f)
    f.close()

while True:
    worlds = get('https://api.wynncraft.com/v3/player').json()

    for player in worlds['players']:
        successful = False
        while not successful:
            try:
                pdata = get(f'https://api.wynncraft.com/v3/player/{player}').json()
            except:
                print(f'Error obtaining data of {player}. SKipping...')
                successful = True
            try:
                first_join = parser.isoparse(pdata['firstJoin'])
                member_for = datetime.now() - first_join.replace(tzinfo=None)
                playtime = pdata['playtime']
                wars = pdata['globalData']['wars']
                total_level = pdata['globalData']['totalLevel']
                if member_for.days == 0:
                    avg_playtime = playtime
                else:
                    avg_playtime = round(playtime / member_for.days, 2)
                if pdata['guild']:
                    guild = pdata["guild"]["name"]
                else:
                    guild = ''
                players_data[player] = {'username': player, 'guild': guild,
                                   'playtime': int(playtime), 'avg_playtime': avg_playtime, 'wars': int(wars), 'total_level': total_level}
                with open('online_players.json', 'w') as f:
                    dump(players_data, f)
                    f.close()
                successful = True
            except Exception as e:
                print(e)
                try:
                    print(f"{pdata['message']}. Retrying to retrieve data of {player} in 20 seconds...")
                    sleep(20)
                except:
                    print(f"Data for player {player} not found. Skipping...")
                    successful = True
        sleep(5)
