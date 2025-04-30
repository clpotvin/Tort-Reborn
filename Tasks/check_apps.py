import datetime
import json
import time

import dateutil
from discord.ext import tasks, commands

from Helpers.database import DB
from Helpers.functions import getPlayerData, getGuildMembers, savePlayers, date_diff


class CheckApps(commands.Cog):
    def __init__(self, client):
        self.client = client

    @tasks.loop(minutes=1)
    async def check_apps(self):
        db = DB()
        db.connect()

        db.cursor.execute('SELECT * FROM new_app WHERE status = \':green_circle: Opened\' AND reminder = FALSE AND posted = TRUE')
        rows = db.cursor.fetchall()

        if len(rows) != 0:
            for row in rows:
                try:
                    channel_id = int(row[0])
                    app_creation = time.mktime(row[5].timetuple())
                    remind_in = app_creation + (3600 * 8)
                    difference = int(time.time()) - app_creation
                    thread_id = int(row[7])
                    ch = self.client.get_channel(channel_id)
                    #print(f'{app_creation}/{remind_in}/{int(time.time())}')
                    if ch.category.name == "Guild Applications" and remind_in <= int(time.time()):
                        thread = self.client.get_channel(thread_id)
                        await thread.send(f"<@&870767928704921651> {int(difference/3600)} hours passed since app creation.")
                        db.cursor.execute(
                            f'UPDATE new_app SET reminder = 1 WHERE channel = \'{channel_id}\'')
                        db.connection.commit()
                except Exception as e:
                    print(f'{rows}\n{row}\n{e}')
        db.close()

    @check_apps.before_loop
    async def guild_log_before_loop(self):
        await self.client.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        print('CheckApps task loaded')
        self.check_apps.start()


def setup(client):
    client.add_cog(CheckApps(client))
