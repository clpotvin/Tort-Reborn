"""Rebuild playtime_daily from the player_activity snapshot history.

The nightly task in update_member_data keeps this current on its own; this
script is for the initial backfill, or for rebuilding after the derivation
rules change. Both share Helpers/playtime_daily so the rules cannot drift.

Safe to re-run: rows are upserted by (uuid, day), so a second pass over
unchanged history is a no-op. Pass --dry-run to report without writing.

    python scripts/backfill_playtime_daily.py [--dry-run] [--since YYYY-MM-DD]
"""
import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Helpers.database import DB
from Helpers.playtime_daily import SOURCE_ROWS, UPSERT, build_rows, MAX_HOURS_PER_DAY  # noqa: F401


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument("--since", help="only write days on or after this date (YYYY-MM-DD)")
    args = parser.parse_args()

    db = DB()
    db.connect()
    try:
        db.cursor.execute(SOURCE_ROWS)
        records = db.cursor.fetchall()
        print(f"read {len(records)} player_activity rows")

        rows = list(build_rows(records))
        if args.since:
            rows = [r for r in rows if str(r[1]) >= args.since]

        by_source = Counter(r[6] for r in rows)
        print(f"built {len(rows)} daily rows covering "
              f"{len({r[1] for r in rows})} distinct days")
        for source, n in sorted(by_source.items()):
            print(f"  {source:<13} {n:>6}")
        print(f"  total hours   {sum(r[2] for r in rows):>10,.0f}")

        if args.dry_run:
            print("\ndry run — nothing written")
            return

        written = 0
        for start in range(0, len(rows), 5000):
            batch = rows[start:start + 5000]
            db.cursor.executemany(UPSERT, batch)
            written += len(batch)
            print(f"  wrote {written}/{len(rows)}", end="\r")
        db.connection.commit()
        print(f"\nwrote {written} rows to playtime_daily")

    finally:
        db.close()


if __name__ == "__main__":
    main()
