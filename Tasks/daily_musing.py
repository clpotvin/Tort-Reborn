"""Daily musing — once per day, at a random time, drops a vague, contemplative
(and sometimes loosely aquatic) thought into the bot-commands channel.

Design notes:
  * At most once per calendar day (UTC). Restart-safe: state lives in bot_settings.
  * The *time* of day is random — each day a target minute is rolled inside an
    active-hours window and persisted, so a restart won't re-roll or double-post.
  * The *content* rotates sequentially through MUSINGS (persisted index), so the
    upcoming order is fully predictable and every line is seen before any repeats.
"""

import asyncio
import datetime
import random

import discord
from discord.ext import tasks, commands

from Helpers.database import DB
from Helpers.logger import log, ERROR, INFO
from Helpers.variables import BOT_COMMAND_CHANNEL_ID, is_home_guild


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Window (UTC, minutes-of-day) in which the daily musing may post. Spans almost
# the whole day — from 30 min after midnight to 30 min before it — so the time
# can genuinely land anywhere, while the 30-min edge buffers keep a late target
# from being missed as the day rolls over.
WINDOW_START_MINUTE = 30            # 00:30
WINDOW_END_MINUTE = 23 * 60 + 30    # 23:30

# bot_settings keys
_LAST_DATE_KEY = "musing_last_post_date"    # YYYY-MM-DD of the last post
_TARGET_DATE_KEY = "musing_target_date"     # YYYY-MM-DD the current target was rolled for
_TARGET_MINUTE_KEY = "musing_target_minute"  # minute-of-day (UTC) to post at
_INDEX_KEY = "musing_index"                 # next index into MUSINGS


# ---------------------------------------------------------------------------
# The musings.
#
# Two groups kept separate so the rotation can alternate between them instead of
# posting one whole group before the other. MUSINGS is built by interleaving:
# aquatic → contemplative → aquatic → contemplative … so each day flips flavor.
# The lists are 1:1 here; make one longer/shorter to change how often water
# themes show up (leftovers from the longer list just tack on at the end).
# ---------------------------------------------------------------------------

AQUATIC = [
    "The ocean does not hurry, yet everything reaches the shore eventually.",
    "A river never sees the sea it is becoming.",
    "Still water and moving water are, in the end, both just water.",
    "The deepest parts of the sea have never needed the sun to know they exist.",
    "Every wave is the whole ocean pretending, for a moment, to be alone.",
    "Fish do not question the water. Perhaps that is their peace.",
    "A single drop remembers nothing of the storm — yet the storm was made of drops.",
    "The tide takes the same shore it gives back. Nothing is truly kept, nothing truly lost.",
    "To float, you first have to stop fighting the water that is already holding you.",
    "The reef is built by creatures who will never see it finished.",
    "What the surface calls a storm, the deep calls a passing mood.",
    "A pearl is only a grain of sand that refused to leave.",
    "The sea remembers every river but keeps none of their names.",
    "Currents move without hands, and still the whole ocean turns.",
    "Even the lighthouse spends most of its life in the dark, pointing toward morning.",
    "Water finds the lowest place, and in doing so, touches everything.",
    "The horizon is not a wall. It is only the edge of how far you have looked.",
    "A boat is safest in the harbor — and that is not what boats are for.",
    "Rain falls on the ocean too, and the ocean does not mind the addition.",
    "We are mostly water, quietly wondering why the sea feels like home.",
    "Somewhere right now a wave is breaking that no one will ever see. It breaks anyway.",
    "The moon pulls the whole ocean and never once touches the water.",
    "Depth and darkness are not the same thing, though we often mistake one for the other.",
    "A ship's wake disappears, but the ship still went somewhere.",
    "We spend our lives learning to swim in a sea we were born already floating in.",
    "The tide will come in again. It always has. There is a quiet kind of faith in that.",
    "Coral, cathedrals, and kindness are all just patient things, becoming.",
    "The smallest fish and the largest whale share the exact same water.",
    "You don't have to understand the current to trust that it is carrying you somewhere.",
    "What we call the deep, the deep simply calls home.",
    "A wave never apologizes for returning to the sea. Neither should you, for going home.",
    "The ocean is old enough to have swallowed a thousand endings and still be full of beginnings.",
]

CONTEMPLATIVE = [
    "Maybe the point was never the destination, but who you became reaching for it.",
    "You are the only person who has ever been exactly you. That has to mean something.",
    "The question you keep avoiding is usually the one worth sitting with.",
    "Time doesn't pass. We do.",
    "A life is just a very long series of small mornings.",
    "Nothing is ever really finished. Some things are just gently set down.",
    "The moment you're waiting for is quietly made of the moments you're ignoring.",
    "To be understood by one person completely is worth more than being known by many.",
    "What you pay attention to is what your life slowly becomes.",
    "Growth rarely feels like growth while it's happening. Mostly it feels like discomfort.",
    "The stars you see tonight may have already gone out. We love things across distances we can't measure.",
    "Being kind costs so little, and somehow no one ever regrets having spent it.",
    "Maybe wonder is just intelligence that hasn't gotten tired yet.",
    "The self you guard so carefully is also the self keeping you from changing.",
    "Almost everything you have ever worried about was, at the time, the most important thing in the world.",
    "You can't step outside your own life to see it clearly — so you might as well live it warmly.",
    "The universe is under no obligation to make sense to us. And yet, sometimes, it almost does.",
    "A candle loses nothing by lighting another.",
    "Perhaps meaning isn't found or given, but quietly made — day by ordinary day.",
    "The people who change us rarely know that they did.",
    "You will not remember most days. You will remember how a few of them felt.",
    "Silence isn't empty. It's just patient.",
    "We might be the way the universe experiences an ordinary afternoon.",
    "Every ending you have survived once looked like the end of everything.",
    "Curiosity is the quietest form of hope.",
    "What if rest is not the reward for the work, but part of it?",
    "The oldest trees grew slowly, in no particular hurry to be admired.",
    "You have already survived every worst day so far. That is a perfect record.",
    "Meaning might just be attention, held long enough to turn into love.",
    "Perhaps the point is simply to be a good ancestor to the person you'll be tomorrow.",
    "Wherever you are going, you are already someone worth arriving.",
    "Maybe being here at all — briefly, quietly — is the whole of it.",
]


def _interleave(a: list[str], b: list[str]) -> list[str]:
    """Alternate a[0], b[0], a[1], b[1], … then append whatever is left over."""
    out = []
    for i in range(max(len(a), len(b))):
        if i < len(a):
            out.append(a[i])
        if i < len(b):
            out.append(b[i])
    return out


MUSINGS = _interleave(AQUATIC, CONTEMPLATIVE)


# ---------------------------------------------------------------------------
# DB helpers (synchronous — run via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _get_setting_sync(key: str) -> str | None:
    db = DB()
    db.connect()
    try:
        db.cursor.execute("SELECT value FROM bot_settings WHERE key = %s", (key,))
        row = db.cursor.fetchone()
        return row[0] if row else None
    finally:
        db.close()


def _set_setting_sync(key: str, value: str):
    db = DB()
    db.connect()
    try:
        db.cursor.execute(
            "INSERT INTO bot_settings (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, value),
        )
        db.connection.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class DailyMusing(commands.Cog):
    def __init__(self, client: discord.Bot):
        self.client = client

    # -- background loop -----------------------------------------------------

    @tasks.loop(minutes=10)
    async def musing_loop(self):
        # Guild restriction: posts only to the home guild's bot-command channel.
        try:
            await self._maybe_post()
        except Exception as e:
            log(ERROR, f"error: {e!r}", context="daily_musing")

    async def _maybe_post(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        today = now.date().isoformat()

        # Already posted today? Nothing to do.
        if await asyncio.to_thread(_get_setting_sync, _LAST_DATE_KEY) == today:
            return

        # Roll (once per day) the random target minute we'll post at.
        target_minute_raw = await asyncio.to_thread(_get_setting_sync, _TARGET_MINUTE_KEY)
        if await asyncio.to_thread(_get_setting_sync, _TARGET_DATE_KEY) != today or target_minute_raw is None:
            target_minute = random.randint(WINDOW_START_MINUTE, WINDOW_END_MINUTE)
            await asyncio.to_thread(_set_setting_sync, _TARGET_MINUTE_KEY, str(target_minute))
            await asyncio.to_thread(_set_setting_sync, _TARGET_DATE_KEY, today)
        else:
            target_minute = int(target_minute_raw)

        # Not time yet.
        if now.hour * 60 + now.minute < target_minute:
            return

        channel = self.client.get_channel(BOT_COMMAND_CHANNEL_ID)
        if channel is None:
            log(ERROR, f"Bot-command channel {BOT_COMMAND_CHANNEL_ID} not found", context="daily_musing")
            return
        if not channel.guild or not is_home_guild(channel.guild.id):
            log(ERROR, f"Bot-command channel {BOT_COMMAND_CHANNEL_ID} not in home guild — skipping", context="daily_musing")
            return

        # Pick the next musing in rotation.
        idx = int(await asyncio.to_thread(_get_setting_sync, _INDEX_KEY) or 0) % len(MUSINGS)
        musing = MUSINGS[idx]

        await channel.send(musing)

        # Persist rotation + mark as posted for today (last, so a failed send retries next tick).
        await asyncio.to_thread(_set_setting_sync, _INDEX_KEY, str((idx + 1) % len(MUSINGS)))
        await asyncio.to_thread(_set_setting_sync, _LAST_DATE_KEY, today)
        log(INFO, f"Posted daily musing #{idx} at {now.strftime('%H:%M')} UTC", context="daily_musing")

    # -- lifecycle -----------------------------------------------------------

    @musing_loop.before_loop
    async def before_loop(self):
        await self.client.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.musing_loop.is_running():
            self.musing_loop.start()


def setup(client):
    client.add_cog(DailyMusing(client))
