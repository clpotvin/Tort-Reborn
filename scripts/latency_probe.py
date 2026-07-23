"""
scripts/latency_probe.py
Cold-path latency repro harness.

Idles, then times each dependency, then immediately times them again warm, and
prints the delta. Runs with no event loop and no background task loops, which is
what makes it useful: a cold/warm delta here is attributable to connection paths
going cold, not to commands queueing behind blocking work in the bot.

Read-only. A SELECT, some GETs, an S3 read, and an in-memory render.

Usage:
    python scripts/latency_probe.py --idle-minutes 10
    python scripts/latency_probe.py --idle-minutes 0   # warm-only, for iterating
"""

import argparse
import os
import sys
import time

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Helpers import telemetry
from Helpers.classes import Guild
from Helpers.database import DB
from Helpers.functions import round_corners, vertical_gradient
from Helpers.storage import get_background


def _time(label, fn):
    start = time.perf_counter()
    error = None
    try:
        fn()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return label, round((time.perf_counter() - start) * 1000.0, 2), error


def _db_select():
    db = DB()
    db.connect()
    try:
        db.cursor.execute("SELECT 1")
        db.cursor.fetchone()
    finally:
        db.close()


def _wynn_fetch():
    Guild("The Aquarium")


def _s3_read():
    get_background(1)


def _render():
    round_corners(vertical_gradient(width=850, height=1130))


STEPS = [
    ("db", _db_select),
    ("wynncraft", _wynn_fetch),
    ("s3", _s3_read),
    ("render", _render),
]


def run_phase(phase):
    results = {}
    for label, fn in STEPS:
        label, ms, error = _time(label, fn)
        results[label] = ms
        telemetry.emit({"type": "probe", "phase": phase, "step": label, "ms": ms, "error": error})
        status = f"  {label:<12} {ms:>9.2f} ms"
        print(status if error is None else f"{status}   ERROR {error}")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--idle-minutes", type=float, default=10.0,
                        help="minutes to idle before the cold pass (default: 10)")
    args = parser.parse_args()

    load_dotenv()

    if args.idle_minutes > 0:
        print(f"Idling {args.idle_minutes} minutes so connection paths go cold...")
        time.sleep(args.idle_minutes * 60.0)

    print("\nCOLD")
    cold = run_phase("cold")

    print("\nWARM")
    warm = run_phase("warm")

    print("\nDELTA (cold - warm)")
    for label, _ in STEPS:
        print(f"  {label:<12} {cold[label] - warm[label]:>9.2f} ms")


if __name__ == "__main__":
    main()
