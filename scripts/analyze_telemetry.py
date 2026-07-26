"""
scripts/analyze_telemetry.py
Summarise Phase 0 latency telemetry from a Railway JSON log dump.

Capture a window (Railway keeps 7 days on the Hobby plan), then analyse it:

    railway logs --service worker --since 48h --lines 5000 --json > phase0.json
    python scripts/analyze_telemetry.py phase0.json

Reads one JSON object per line (Railway flattens each emitted telemetry record
into top-level attributes) and prints, in the order the investigation doc says
to read them:

  1. event-loop drift  (loop_lag_summary  -> is the loop congested?)
  2. drift excursions  (loop_lag          -> what blocks it, and when?)
  3. command breakdown (command           -> where does a command's time go?)

Reads from a file argument, or stdin if none is given. Read-only.
"""

import json
import sys
from statistics import median


def _load(stream):
    summaries, excursions, commands, loop_starts = [], [], [], []
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        t = rec.get("type")
        if t == "loop_lag_summary":
            summaries.append(rec)
        elif t == "loop_lag":
            excursions.append(rec)
        elif t == "command":
            commands.append(rec)
        elif "STARTING LOOP" in (rec.get("message") or ""):
            loop_starts.append(rec)
    return summaries, excursions, commands, loop_starts


def _pct(values, q):
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return s[idx]


def _buckets(rec):
    b = rec.get("buckets") or {}
    if isinstance(b, str):
        try:
            b = json.loads(b)
        except ValueError:
            b = {}
    return b


def _span(records):
    ts = [r.get("timestamp", "") for r in records if r.get("timestamp")]
    return (min(ts), max(ts)) if ts else ("?", "?")


def report(summaries, excursions, commands, loop_starts):
    everything = summaries + excursions + commands + loop_starts
    lo, hi = _span(everything)
    print(f"Window: {lo}  ->  {hi}")
    print(f"Records: {len(summaries)} summaries, {len(excursions)} excursions, "
          f"{len(commands)} commands\n")

    # 1. Loop health
    print("== Event-loop drift (loop_lag_summary) ==")
    if summaries:
        p95 = [s.get("p95_ms", 0) for s in summaries]
        mx = [s.get("max_ms", 0) for s in summaries]
        print(f"  windows            {len(summaries)}")
        print(f"  p95 drift  median  {median(p95):.2f} ms")
        print(f"  p95 drift  p90     {_pct(p95, 0.90):.2f} ms")
        print(f"  p95 drift  max     {max(p95):.2f} ms")
        print(f"  windows w/ max-tick >100ms  {sum(1 for m in mx if m > 100)}")
        print(f"  windows w/ max-tick >250ms  {sum(1 for m in mx if m > 250)}")
        print(f"  windows w/ max-tick >1000ms {sum(1 for m in mx if m > 1000)}")
    else:
        print("  (none)")

    # 2. Excursions and what they line up with
    print("\n== Drift excursions (loop_lag > threshold) ==")
    if excursions:
        drifts = [e.get("drift_ms", 0) for e in excursions]
        cmd_ts = sorted(c.get("ts", 0) for c in commands)

        def near_command(ts):
            return any(abs(ts - c) < 3 for c in cmd_ts)

        def in_task_window(rec):
            # update_member_data and siblings fire around :34-:40 of the minute
            sec = rec.get("timestamp", "")[17:19]
            return sec.isdigit() and 34 <= int(sec) <= 40

        by_cmd = sum(1 for e in excursions if near_command(e.get("ts", 0)))
        by_task = sum(1 for e in excursions
                      if in_task_window(e) and not near_command(e.get("ts", 0)))
        print(f"  count   {len(excursions)}   range {min(drifts):.0f}-{max(drifts):.0f} ms")
        print(f"  coincide with a command (±3s)      {by_cmd}   (usually the largest)")
        print(f"  land in the task-loop second window  {by_task}")
        print(f"  other                                {len(excursions) - by_cmd - by_task}")
        print("  largest:")
        for e in sorted(excursions, key=lambda x: -x.get("drift_ms", 0))[:5]:
            tag = "  <- command" if near_command(e.get("ts", 0)) else ""
            print(f"    {e.get('timestamp','?')[11:19]}  {e.get('drift_ms',0):>6.0f} ms{tag}")
    else:
        print("  (none)")

    # 3. Commands
    print("\n== Commands ==")
    if commands:
        nulls = sum(1 for c in commands if c.get("queue_ms") is None)
        if nulls:
            print(f"  NOTE: queue_ms is null on {nulls}/{len(commands)} records\n")
        print(f"  {'time':<9} {'command':<16} {'queue':>7} {'total':>7}   top buckets")
        for c in sorted(commands, key=lambda x: x.get("timestamp", "")):
            t = c.get("timestamp", "?")[11:19]
            q = c.get("queue_ms")
            q = "null" if q is None else f"{q:.0f}"
            top = sorted(_buckets(c).items(), key=lambda kv: -kv[1].get("ms", 0))[:3]
            tops = ", ".join(f"{k}={v.get('ms',0):.0f}" for k, v in top)
            print(f"  {t:<9} {c.get('command','?'):<16} {q:>7} "
                  f"{c.get('total_ms',0):>7.0f}   {tops}")
    else:
        print("  (none)")


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as fh:
            data = _load(fh)
    else:
        data = _load(sys.stdin)
    report(*data)


if __name__ == "__main__":
    main()
