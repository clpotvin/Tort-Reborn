# Command latency investigation

**Status:** parked. Investigation only — no code changes made. Pick up at [Phase 0](#phase-0--measure-first) when this becomes a priority.

## Symptom

After a quiet period, the first slash command takes a very long time to return. Subsequent
commands are noticeably faster for a while, then the slowness returns. The pattern reads as
something "going to sleep" and needing to wake up.

## Architecture snapshot

Single Railway **worker** service — one process, one event loop, one persistent Discord gateway
socket (see `Procfile`, `main.py`). No public port.

| Dependency | Access pattern | Entry point |
|---|---|---|
| Neon Postgres (pooler endpoint) | psycopg2, one connect+close **per helper call** | `DB` in `Helpers/database.py` |
| Supabase Storage (S3 API) | boto3, lazily-created singleton client | `S3Storage` in `Helpers/storage.py` |
| Wynncraft v3 / Mojang / visage / Athena | blocking `requests.get`, new session per call | `Helpers/functions.py`, `Guild` in `Helpers/classes.py` |
| OpenAI, Google Sheets | blocking | `Helpers/openai_helper.py`, `Helpers/sheets.py` |

Sharing that one event loop: the command cogs in `Commands/`, the task loops in `Tasks/`
(intervals from 10s to daily), and Pillow card rendering.

## Ruled out

The "something is asleep" model does not survive the evidence:

- **Neon autosuspend.** `Tasks/territory_tracker.py` runs on a 10-second loop and opens two fresh
  Neon connections per pass (`_read_territories_sync`, `saveTerritoryData`). Autosuspend requires
  several minutes of zero compute activity. The database never gets there.
- **Railway app sleep.** Sleep applies to HTTP-triggered services. This is a worker with no public
  port and a permanently open gateway socket. If sleep were active the bot would disconnect
  outright rather than merely slow down.
- **In-process caches expiring.** The `lru_cache` font cache and UUID/name cache in
  `Helpers/functions.py`, and the Athena guild-colour cache in `Commands/snipe.py`, live for the
  process lifetime or hours. None of them cycle on the timescale of the reported symptom.

## Hypotheses, ranked

**H1 — Event-loop contention with the background task fleet.** *(best fit)*
The task loops in `Tasks/` run on 1/2/3/5/10-minute cycles and several perform blocking work
directly on the event loop. A command arriving mid-cycle queues behind that work; one arriving in
a gap returns immediately. The apparent sleep/wake periodicity is the task schedule.
`Tasks/update_member_data.py` is the prime suspect — it runs every three minutes and iterates the
full guild roster.

**H2 — Cold connection paths after idle.** *(contributing)*
Every database helper opens a fresh TLS connection to Neon. Every outbound API call builds a new
`requests` session, so nothing reuses a socket. botocore's connection pool idles out. Under
sustained traffic some of this amortises; after a quiet spell everything re-handshakes at once. A
single `/profile` invocation can open several Neon connections and several TLS sessions.

**H3 — Upstream edge-cache misses.** *(external)*
A cold Wynncraft API cache for a given player accounts for part of the first-call cost. Not
fixable here; worth measuring so it can be subtracted from the budget.

## Structural problems found

These are worth fixing regardless of which hypothesis wins.

1. **No database connection pool.** Every helper in `Helpers/database.py` constructs a `DB`,
   connects, and closes. One command can pay that cost five or more times. A process-lifetime
   `ThreadedConnectionPool` (or a move to `psycopg_pool`) removes it.
2. **Blocking I/O on the event loop.** Many `requests.get` call sites live in `Commands/`.
   `Commands/profile.py` is representative: it correctly moves `PlayerStats` to a thread, then
   fetches the avatar synchronously, hits S3 synchronously, and renders the Pillow card inline.
   This stalls the gateway heartbeat, not just other commands.
3. **No shared HTTP session.** There is no keep-alive anywhere in the outbound path.
4. **No latency instrumentation.** Nothing measures where time goes, so everything above is
   inference rather than measurement. This is the real blocker.

## Plan

### Phase 0 — measure first

Do not fix anything until these land and produce a deploy cycle's worth of data.

- **Event-loop lag monitor.** A one-second task recording scheduling drift. If lag spikes into the
  seconds on the three-minute boundary, H1 is confirmed and the rest is secondary.
- **Per-command timing.** Wrap command invocation to log total wall time, split by boundary:
  database connect vs. query, each outbound host, S3, render.
- **Correlation.** Line slow commands up against task-loop start times. `update_member_data`
  already logs a loop-start marker.

Estimated at well under a hundred lines.

### Phase 1 — fixes, highest payoff first

1. Connection pool in `DB`. Single file, removes N handshakes per command.
2. Move remaining blocking work off the loop: module-level `requests.Session`, and `to_thread` for
   the Pillow render and the S3 calls.
3. Stagger task-loop start offsets so they do not all fire on the same minute boundary.
4. Split the task fleet into its own service or process so background work cannot contend with
   interaction handling. This is the real fix for H1 and the largest change — only worth doing if
   Phase 0 confirms H1.

## Picking this back up

Start at Phase 0. The single highest-information measurement is the event-loop lag monitor: it
either confirms or kills H1 in one deploy, and that decides whether Phase 1 step 4 is needed at
all.
