import datetime
import requests
import json
import time

from discord.ext import tasks, commands

from Helpers.variables import test


def getTerritoryData():
    url = 'https://api.wynncraft.com/v3/guild/list/territory'
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return False
    except ValueError:
        return False


def saveTerritoryData(data):
    with open('territories.json', 'w') as f:
        json.dump(data, f, indent=4)
        f.close()


def timeHeld(date_time_old, date_time_new):
    t_old = datetime.datetime.fromisoformat(date_time_old[0:len(date_time_old) - 1])
    t_new = datetime.datetime.fromisoformat(date_time_new[0:len(date_time_new) - 1])
    t_held = t_new.__sub__(t_old)

    d = t_held.days
    td = datetime.timedelta(seconds=t_held.seconds)
    t = str(td).split(":")

    return f"{d} d {t[0]} h {t[1]} m {t[2]} s"


class TerritoryTracker(commands.Cog):
    def __init__(self, client):
        self.client = client

    @tasks.loop(seconds=10)
    async def territory_tracker(self):
        try:
            if not test:
                channel = self.client.get_channel(729162480000958564)
                military_channel = self.client.get_channel(729162690760671244)
                spearhead = 857589881689210950
            else:
                channel = self.client.get_channel(1367287144682487828)  # test
                military_channel = self.client.get_channel(1367287144682487828)  # test
                spearhead = 1367287262068342804  # test
        except:
            pass

        with open('territories.json', 'r') as f:
            old_terr_data = json.load(f)
            f.close()
        with open('claim.json', 'r') as f:
            claim = json.load(f)
            f.close()

        new_terr_data = getTerritoryData()
        if not new_terr_data:
            print("Something went wrong with fetching territory data...")
            return
        else:
            saveTerritoryData(new_terr_data)

            owner_changes = {}
            terr_count = {'old': [], 'new': []}

            for terr in old_terr_data:
                if old_terr_data[terr]['guild']['name'] not in terr_count['old']:
                    terr_count['old'].append(old_terr_data[terr]['guild']['name'])
                    terr_count['old'].append(1)
                else:
                    terr_count['old'][terr_count['old'].index(old_terr_data[terr]['guild']['name']) + 1] += 1

            for terr in new_terr_data:
                if new_terr_data[terr]['guild']['name'] not in terr_count['new']:
                    terr_count['new'].append(new_terr_data[terr]['guild']['name'])
                    terr_count['new'].append(1)
                else:
                    terr_count['new'][terr_count['new'].index(new_terr_data[terr]['guild']['name']) + 1] += 1

                if new_terr_data[terr]['guild']['name'] != old_terr_data[terr]['guild']['name']:
                    owner_changes.update({terr: {'old': {'owner': old_terr_data[terr]['guild']['name'],
                                                         'prefix': old_terr_data[terr]['guild']['prefix'],
                                                         'acquired': old_terr_data[terr]['acquired']},
                                                 'new': {'owner': new_terr_data[terr]['guild']['name'],
                                                         'prefix': new_terr_data[terr]['guild']['prefix'],
                                                         'acquired': new_terr_data[terr]['acquired']}}})

            for terr in owner_changes:
                if terr in claim['conns'] and owner_changes[terr]['old']['owner'] == 'The Aquarium':
                    global last_ping
                    called = time.time()

                    try:
                        time_since_ping = called - last_ping
                    except NameError as e:
                        last_ping = 0
                        time_since_ping = called - last_ping

                    if time_since_ping > 1800:
                        last_ping = called
                        try:
                            print("Spearhead Ping")
                            await military_channel.send(f"<@&{spearhead}> {terr} has been taken by {owner_changes[terr]['new']['owner']} [{owner_changes[terr]['new']['prefix']}]!")
                        except Exception as e:
                            print(e)
                            pass

                if owner_changes[terr]['old']['owner'] == 'The Aquarium' or owner_changes[terr]['new']['owner'] == 'The Aquarium' or (owner_changes[terr] in claim['territories']):
                    held_for = timeHeld(owner_changes[terr]['old']['acquired'], owner_changes[terr]['new']['acquired'])
                    try:
                        print("Updating Territory")
                        await channel.send(f'**{terr}**: {owner_changes[terr]["old"]["owner"]} ({str(terr_count["old"][terr_count["old"].index(owner_changes[terr]["old"]["owner"]) + 1])}) → {owner_changes[terr]["new"]["owner"]} ({str(terr_count["new"][terr_count["new"].index(owner_changes[terr]["new"]["owner"]) + 1])}) \n\tTerritory held for {held_for}')
                    except Exception as e:
                        print("Could not output to tracking channel.")
                        pass

    @territory_tracker.before_loop
    async def territory_tracker_before_loop(self):
        await self.client.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        print('TerritoryTracker task loaded')
        saveTerritoryData(getTerritoryData())
        self.territory_tracker.start()


def setup(client):
    client.add_cog(TerritoryTracker(client))
