import json
import time
import urllib.request
from datetime import datetime

import schedule
from dotenv import load_dotenv

from Helpers.classes import Guild
from Helpers.database import DB
from Helpers.functions import getPlayerDatav3

load_dotenv()


def job():
    today = datetime.today()

    if today.weekday() == 6:
        with open('button_cd.json', 'w') as f:
            json.dump({}, f)
            f.close()
        with open('eco_cd.json', 'w') as f:
            json.dump({}, f)
            f.close()

    data = Guild('The Aquarium').all_members

    memberlist = {'time': int(time.mktime(datetime.now().timetuple())), 'members': []}
    db = DB()
    db.connect()
    for member in data:
        success = False
        while not success:
            try:
                mber = getPlayerDatav3(member['uuid'])

                db.cursor.execute(
                    f'SELECT discord_links.ign, COALESCE(shells.shells, 0) AS shells FROM discord_links LEFT JOIN shells ON discord_links.discord_id = shells.user WHERE discord_links.uuid = \'{member["uuid"]}\';')
                row = db.cursor.fetchone()
                if row:
                    shells = row[1]
                else:
                    shells = 0
                memberlist['members'].append(
                    {"name": mber['username'], "uuid": mber['uuid'], "rank": member['rank'],
                     "playtime": mber['playtime'], "contributed": member['contributed'],
                     'wars': mber['globalData']['wars'], 'shells': shells})
                print(
                    f"{mber['username']} {member['rank']} {mber['playtime']} {member['contributed']} {mber['globalData']['wars']} {shells}")
                success = True
            except Exception as e:
                print(e)
                print(f'Could not get data for {member["name"]}. Retrying in 30 seconds.')
                time.sleep(30)
        time.sleep(3)

    with open("activity2.json", 'r') as f:
        old_data = json.loads(f.read())
        old_data.insert(0, memberlist)
        with open("activity2.json", 'w') as f:
            json.dump(old_data[:60], f)
    db.close()


schedule.every().day.at("22:52").do(job)

while True:
    schedule.run_pending()
    time.sleep(60)
