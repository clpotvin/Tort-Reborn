import discord
from discord.ext import commands
from discord.commands import user_command

from Helpers.classes import BasicPlayerStats
from Helpers.database import DB
from Helpers.variables import guilds


class ResetRoles(commands.Cog):
    def __init__(self, client):
        self.client = client

    @user_command(name='Member | Remove', default_member_permissions=discord.Permissions(manage_roles=True), guild_ids=guilds)
    async def reset_roles(self, message, user):
        if message.interaction.user.guild_permissions.manage_roles:
            await message.defer(ephemeral=True)
            db = DB()
            db.connect()
            db.cursor.execute(f'SELECT * FROM discord_links WHERE discord_id = \'{user.id}\'')
            row = db.cursor.fetchone()
            pdata = False
            if row:
                pdata = BasicPlayerStats(row[2])
            all_roles = message.interaction.guild.roles
            to_remove = ['Member', 'The Aquarium [TAq]', '☆Reef', 'Starfish', 'Manatee', '★Coastal Waters', 'Piranha',
                         'Barracuda', '★★ Azure Ocean', 'Angler', '★☆☆ Blue Sea', 'Hammerhead', '★★☆Deep Sea',
                         'Sailfish', '★★★Dark Sea', 'Dolphin', 'Trial-Chief', 'Narwhal', '★★★★Abyss Waters',
                         '🛡️MODERATOR⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀', '🛡️SR. MODERATOR⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀',
                         '🥇 RANKS⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀', '🛠️ PROFESSIONS⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀',
                         '✨ COSMETIC ROLES⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀', '🎖️MILITARY⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀', '🏹Spearhead',
                         '⚠️Standby', '🗡️FFA', 'DPS', 'Tank', 'Healer', 'Orca', 'War News', 'EcoFish']
            roles_to_remove = []
            to_add = ['Ex-Member']
            roles_to_add = []

            for add_role in to_add:
                role = discord.utils.find(lambda r: r.name == add_role, all_roles)
                if role not in user.roles:
                    roles_to_add.append(role)

            await user.add_roles(*roles_to_add, reason=f'Roles reset (ran by {message.author.name})')

            for remove_role in to_remove:
                role = discord.utils.find(lambda r: r.name == remove_role, all_roles)
                if role in user.roles:
                    roles_to_remove.append(role)

            await user.remove_roles(*roles_to_remove, reason=f'Roles reset (ran by {message.author.name})')
            await user.edit(nick='')

            if pdata:
                db.cursor.execute(
                    f'UPDATE discord_links SET guild_wars = {pdata.wars - row[5] + row[6]} WHERE discord_id = \'{user.id}\'')
                db.connection.commit()

            db.close()
            embed = discord.Embed(title=':white_check_mark: Roles reset',
                                  description=f'Roles were reset for <@{user.id}>', color=0x3ed63e)
            await message.respond(embed=embed)
        else:
            await message.respond('You are missing Manage Roles permission(s) to run this command.')

    @commands.Cog.listener()
    async def on_ready(self):
        print('ResetRoles user command loaded')


def setup(client):
    client.add_cog(ResetRoles(client))
