import json
import time
import urllib.request
from datetime import datetime

import schedule


with urllib.request.urlopen(
        "https://api.wynncraft.com/public_api.php?action=guildStats&command=The%20Aquarium") as url:
    data = json.loads(url.read().decode())
memberlist = {'time': int(time.mktime(datetime.now().timetuple())), 'members': []}
for member in data['members']:
    success = False
    while not success:
        try:
            with urllib.request.urlopen("https://api.wynncraft.com/v2/player/" + member['uuid'] + "/stats") as url:
                mber = json.loads(url.read().decode())
            memberlist['members'].append(
                {"name": mber['data'][0]['username'], "uuid": mber['data'][0]['uuid'], "rank": member['rank'],
                 "playtime": mber['data'][0]['meta']['playtime'], "contributed": member['contributed']})
            print(mber['data'][0]['username'] + ' ' + member['rank'] + ' ' + str(
                    mber['data'][0]['meta']['playtime']))
            success = True
        except Exception as e:
            print(e)
            print(f'Could not get data for {member["name"]}. Retrying in 30 seconds.')
            time.sleep(30)
    time.sleep(3)
with open("../activity2.json", 'r') as f:
    old_data = json.loads(f.read())
    old_data.insert(0, memberlist)
    with open("../activity2.json", 'w') as f:
        json.dump(old_data, f)