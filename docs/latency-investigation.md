# Command latency investigation

**Status:** Phase 0 instrumentation is implemented (measurement only, behaviourally neutral). It has not yet been analysed — deploy, capture a data window, then work through [Reading the telemetry](#reading-the-telemetry). Phase 1 (the fixes) has not been started.

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
4. **No latency instrumentation.** Nothing measured where time goes, so everything above is
   inference rather than measurement. This is the gap Phase 0 closes.

## Plan

### Phase 0 — measure (implemented)

Instrumentation is in place. It is measurement-only and behaviourally neutral: it wraps existing
code and times it, changing no runtime behaviour, so the numbers form a valid baseline to judge
Phase 1 against. Toggle with the `LATENCY_TELEMETRY` env var — any of `0` / `false` / `no`
(case-insensitive) disables it; default on.

What it emits — one JSON line per record to **stdout** (deliberately not the Discord log channel,
so it never spams `#logs`):

- `command` — one per slash-command invocation: `queue_ms` (the gap between Discord creating the
  interaction and the bot starting to run it), `total_ms`, `ok`, and `buckets` splitting time by
  `db.connect` / `db.query` / `db.commit` / `http.<host>` / `s3.get` / `s3.put` / `render`.
- `loop_lag` — emitted whenever a single one-second tick drifts more than 250 ms.
- `loop_lag_summary` — once a minute: p50 / p95 / max drift.
- `probe` — only when `scripts/latency_probe.py` is run by hand (idle → cold timings → warm
  timings → delta). Read-only, and not part of the deployed bot.

Scope limits to keep in mind when reading the data:

- Timing records are **command-scoped**. Background task loops call the same DB and HTTP layers but
  run outside any command, so their own calls emit no bucket record. Their impact shows up
  indirectly, through `loop_lag` and through `queue_ms` on commands that land mid-cycle.
- A few `requests.get` calls inside individual command files (snipe, worlds, lootpool, manage,
  raids, map, progress) are not routed through the timed wrapper, so their HTTP time appears in no
  `http.*` bucket. The shared hot paths are covered; the picture is not exhaustive.
- A command cancelled mid-flight (shutdown, gateway disconnect) records `ok: true`, because
  py-cord swallows the cancellation before the timing hook runs. Documented, not fixed.

### Reading the telemetry

Read stdout in this order:

1. `loop_lag_summary` p95 first. Seconds-scale drift means the event loop is being blocked — direct
   support for H1.
2. `queue_ms` outliers on `command` records, cross-referenced against task-loop start times
   (`update_member_data` logs a `STARTING LOOP` marker).
3. Only if those look clean, the `buckets` split on the slowest `command` records.
4. `scripts/latency_probe.py --idle-minutes 10` (or more), run separately, to settle H2 on its own
   terms: it runs with no event loop and no task loops, so a cold/warm delta there is attributable
   to connections going cold rather than to loop contention.

The decision that falls out: whether Phase 1 needs the task fleet split off the event loop (H1), or
whether pooling and HTTP session reuse are enough (H2).

### Capturing the data (Railway retention)

Railway keeps logs for a limited window by plan — 7 days on Hobby, 30 on Pro. Telemetry lands on
the same stdout stream as the normal logs, interleaved; filter with
`railway logs | grep '"type":' | jq`.

Two consequences:

- The measurement window must fit inside retention. This is an active, bounded measurement (cycles
  are minutes-to-hours apart, so a couple of days suffices), so 7 days is enough — but don't deploy
  and leave it; the early data ages out.
- Anything worth keeping past the window — in particular the baseline run to diff Phase 1 against —
  must be pulled down deliberately: `railway logs > phase0-baseline.jsonl` during the run, or
  forward logs to an external sink (Railway suggests Vector / Fluent Bit / OTEL). For a one-off
  investigation, teeing to a file is enough; a forwarder is overkill.

### Phase 1 — fixes, highest payoff first

1. Connection pool in `DB`. Single file, removes N handshakes per command.
2. Move remaining blocking work off the loop: module-level `requests.Session`, and `to_thread` for
   the Pillow render and the S3 calls.
3. Stagger task-loop start offsets so they do not all fire on the same minute boundary.
4. Split the task fleet into its own service or process so background work cannot contend with
   interaction handling. This is the real fix for H1 and the largest change — only worth doing if
   Phase 0 confirms H1.

## Picking this back up

Phase 0 is built and deployed-ready; the next action is to run it and read the output, not to write
more code. Deploy, let it run through several quiet-then-active cycles, capture the window before it
ages out, then work through [Reading the telemetry](#reading-the-telemetry). The single
highest-information signal is the event-loop lag monitor: it either confirms or kills H1, and that
decides whether Phase 1's task-fleet split is needed at all.
