# Command latency investigation

**Status:** Phase 0 is deployed and the first two days have been analysed — see [Findings](#findings--first-two-days-of-telemetry). The measured result promotes H2 (cold connections) over H1 and rescopes the fixes; [Phase 1](#phase-1--fixes-evidence-ranked) is evidence-ranked and not yet started.

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

*This was the ranking before any measurement. The [Findings](#findings--first-two-days-of-telemetry)
section has the measured result, which reordered these: H2 is the dominant cost and H1 is
secondary.*

**H1 — Event-loop contention with the background task fleet.** *(pre-measurement: best guess)*
The task loops in `Tasks/` run on 1/2/3/5/10-minute cycles and several perform blocking work
directly on the event loop. A command arriving mid-cycle queues behind that work; one arriving in
a gap returns immediately. The apparent sleep/wake periodicity is the task schedule.
`Tasks/update_member_data.py` is the prime suspect — it runs every three minutes and iterates the
full guild roster.

**H2 — Cold connection paths after idle.** *(pre-measurement: contributing; measured: dominant)*
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

### Findings — first two days of telemetry

Measured over roughly the first day and a half after deployment (~1,800 one-minute drift windows,
~70 drift excursions, 15 commands). Low command traffic, which is itself part of the story.

- **The event loop is healthy at baseline.** p95 drift is ~2 ms (median across all windows), p90
  ~2.5 ms. A congested loop is ruled out. Brief single-tick bumps occur (about a quarter of minutes
  touch >100 ms once) but nothing sustained.
- **Every command is slow — 2 to 6.5 seconds — and the cost is cold external I/O.** Supabase S3
  reads dominate: `s3.get` ranged 0.7–4.0 s. Then outbound HTTP (visage avatar, Wynncraft) and
  fresh DB connects (0.1–0.7 s each, no pool).
- **H2 (cold connections) is confirmed on real traffic.** Two `profile` calls a minute apart showed
  `s3.get` drop from ~3.95 s to ~0.73 s — a ~5× cold penalty. With traffic this sparse, paths are
  almost always cold, so nearly every command is a first-after-idle. That is the reported symptom.
- **Commands block the loop themselves.** The largest drift excursions (up to ~5.1 s) coincide with
  commands, because the card-render path runs S3, HTTP and Pillow inline on the event loop. A slow
  command stalls the loop for everyone during it.
- **H1 (task contention) is real but secondary.** About half the excursions are
  `update_member_data`'s recurring ~300 ms stalls; the rest are other task loops. None of this is
  the main driver of command latency.

The data redirects Phase 1: the event loop is not congested, so **splitting the task fleet into its
own service — the largest planned change — is not justified.** The win is getting command I/O off
the loop and making it not-cold.

### Phase 1 — fixes, evidence-ranked

1. **Get command I/O off the loop and de-cold it.** Highest payoff, addresses both the slow command
   and the loop stalls it causes:
   - `to_thread` the blocking S3 / avatar-fetch / Pillow work in `profile` and the other card
     commands.
   - Attack the S3 cost directly — it is the fattest bucket by far. Backgrounds and avatars are
     near-static, and the avatar's 3-day cache currently lives in S3, so the cache *read* itself
     costs 0.7–1.6 s. Move that cache to local disk or an in-process LRU.
   - Connection pool in `DB` (removes the per-command connect cost) and a warm/keepalive HTTP
     session (helps visage / Wynncraft).
2. **Stagger task-loop start offsets** so `update_member_data` and siblings do not all fire on the
   same minute boundary — cheap mitigation for the ~300 ms task stalls.
3. **Split the task fleet into its own service** — parked. Not justified while the loop is healthy;
   revisit only if traffic grows enough to congest it.

`queue_ms` recorded null for every command in the first window because `discord.Interaction`
(py-cord 2.6) has no `created_at`; it is now derived from the interaction snowflake id, so the
queue-delay discriminator works from the next deploy onward.

## Picking this back up

Phase 0 is deployed and the first read is done (see Findings). Re-run the analysis on a fresh
capture with `scripts/analyze_telemetry.py` (it prints drift health, excursion correlation, and the
per-command bucket breakdown from a `railway logs --json` dump), then start Phase 1 at item 1 —
threading the card-command I/O and moving the S3 background/avatar cache off S3. Keep the `db.*` /
`s3.*` / `http.*` bucket names stable through the fixes so before/after captures stay comparable.
