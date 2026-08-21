"""Fold 15-minute presence buckets into hourly rollups, and prune the raw.

The sampler in update_member_data writes one bucket row per member per 15
minutes. That is the right grain to collect at and the wrong grain to chart a
year from, so this task folds completed hours into presence_hourly (per
member) and presence_coverage_hourly (guild-wide), then drops raw buckets past
the retention window.

Converting samples to minutes is where the tick log earns its place. A sample
is not worth a fixed three minutes: it is worth 15 / (ticks observed in its
bucket), so an hour the loop only half-covered reports the presence it did see
stretched over the interval it stands for, instead of reading as a quiet hour.
An hour with no ticks at all produces no rows — a gap the charts can draw as a
gap.

Only whole hours that have passed are rolled up, so the current hour is never
written half-finished and then left stale.
"""
import asyncio
import datetime
from datetime import timezone, timedelta

from discord.ext import tasks, commands

from Helpers.database import DB
from Helpers.logger import log, ERROR, INFO

# Raw buckets are kept long enough to re-derive an hour if the rollup logic
# changes; beyond that the hourly tables are the record.
RAW_RETENTION_DAYS = 90

# Guards a cold start (or a long outage) from scanning the whole table.
MAX_HOURS_PER_RUN = 168

ROLLUP_SQL = """
WITH bounds AS (
    SELECT %s::timestamptz AS from_hour, %s::timestamptz AS to_hour
),
-- Ticks actually recorded inside each 15-minute bucket. This is the divisor
-- that turns a sample count into minutes.
bucket_ticks AS (
    SELECT date_bin('15 minutes', tick_at, TIMESTAMPTZ '2000-01-01') AS bucket_start,
           COUNT(*)::int AS ticks
    FROM presence_ticks, bounds
    WHERE tick_at >= bounds.from_hour AND tick_at < bounds.to_hour
    GROUP BY 1
),
member_minutes AS (
    SELECT b.uuid,
           date_trunc('hour', b.bucket_start) AS hour,
           SUM(LEAST(b.samples::real * 15.0 / t.ticks, 15.0)) AS minutes
    FROM presence_buckets b
    JOIN bucket_ticks t ON t.bucket_start = b.bucket_start
    CROSS JOIN bounds
    WHERE b.bucket_start >= bounds.from_hour AND b.bucket_start < bounds.to_hour
    GROUP BY 1, 2
),
inserted_members AS (
    INSERT INTO presence_hourly (uuid, hour, minutes)
    SELECT uuid, hour, minutes FROM member_minutes
    ON CONFLICT (uuid, hour) DO UPDATE SET minutes = EXCLUDED.minutes
    RETURNING 1
),
-- online_avg comes from the guild's own count so hidden members are included;
-- attributed_avg is the subset presence_buckets could name. Charting the first
-- and drilling into the second is the whole reason both are stored.
coverage AS (
    SELECT date_trunc('hour', tick_at)  AS hour,
           COUNT(*)::int                AS ticks_observed,
           AVG(online_count)::real      AS online_avg,
           MAX(online_count)::int       AS online_peak,
           AVG(attributed_count)::real  AS attributed_avg
    FROM presence_ticks, bounds
    WHERE tick_at >= bounds.from_hour AND tick_at < bounds.to_hour
    GROUP BY 1
),
distinct_members AS (
    SELECT hour, COUNT(*)::int AS members FROM member_minutes GROUP BY hour
),
inserted_coverage AS (
    INSERT INTO presence_coverage_hourly
        (hour, ticks_observed, online_avg, online_peak, distinct_members, attributed_avg)
    SELECT c.hour, c.ticks_observed, c.online_avg, c.online_peak,
           COALESCE(d.members, 0), c.attributed_avg
    FROM coverage c LEFT JOIN distinct_members d ON d.hour = c.hour
    ON CONFLICT (hour) DO UPDATE SET
        ticks_observed   = EXCLUDED.ticks_observed,
        online_avg       = EXCLUDED.online_avg,
        online_peak      = EXCLUDED.online_peak,
        distinct_members = EXCLUDED.distinct_members,
        attributed_avg   = EXCLUDED.attributed_avg
    RETURNING 1
)
SELECT (SELECT COUNT(*) FROM inserted_members),
       (SELECT COUNT(*) FROM inserted_coverage)
"""


def _rollup_sync():
    """Roll up every whole hour not yet covered. Returns a summary string."""
    db = DB()
    db.connect()
    try:
        now = datetime.datetime.now(timezone.utc)
        current_hour = now.replace(minute=0, second=0, microsecond=0)

        # Resume from the last rolled-up hour; on a cold start, from the
        # oldest raw tick.
        db.cursor.execute("SELECT MAX(hour) FROM presence_coverage_hourly")
        row = db.cursor.fetchone()
        last_hour = row[0] if row else None

        if last_hour is None:
            db.cursor.execute("SELECT MIN(tick_at) FROM presence_ticks")
            row = db.cursor.fetchone()
            if not row or row[0] is None:
                return "no presence data yet"
            from_hour = row[0].replace(minute=0, second=0, microsecond=0)
        else:
            # Recompute the most recent rolled-up hour: it may have been
            # written while still in progress on the previous run.
            from_hour = last_hour

        to_hour = min(current_hour, from_hour + timedelta(hours=MAX_HOURS_PER_RUN))
        if to_hour <= from_hour:
            return "already current"

        db.cursor.execute(ROLLUP_SQL, (from_hour, to_hour))
        members, hours = db.cursor.fetchone()

        cutoff = current_hour - timedelta(days=RAW_RETENTION_DAYS)
        db.cursor.execute("DELETE FROM presence_buckets WHERE bucket_start < %s", (cutoff,))
        pruned_buckets = db.cursor.rowcount
        db.cursor.execute("DELETE FROM presence_ticks WHERE tick_at < %s", (cutoff,))
        pruned_ticks = db.cursor.rowcount

        db.connection.commit()
        # Postgres hands back timestamps in the session timezone; the rollup
        # reasons in UTC, so say so rather than logging a shifted hour.
        span = (f"{from_hour.astimezone(timezone.utc):%Y-%m-%d %H:%M} → "
                f"{to_hour.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC")
        return (f"{span}: {members} member-hours, {hours} coverage hours, "
                f"pruned {pruned_buckets} buckets / {pruned_ticks} ticks")
    finally:
        db.close()


class PresenceRollup(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.presence_rollup.start()

    def cog_unload(self):
        self.presence_rollup.cancel()

    @tasks.loop(minutes=20)
    async def presence_rollup(self):
        try:
            summary = await asyncio.to_thread(_rollup_sync)
            log(INFO, summary, context="presence_rollup")
        except Exception as e:
            log(ERROR, f"Presence rollup failed: {e}", context="presence_rollup")

    @presence_rollup.before_loop
    async def before_rollup(self):
        await self.client.wait_until_ready()


def setup(client):
    client.add_cog(PresenceRollup(client))
