"""One-off sweep: strip lingering guild roles from everyone holding Ex-Member.

Before TAQ-67 the removal flows worked from stale role lists (renamed
CONTRIBUTION header, missing military block, missing HQ Team / staff roles),
so hundreds of ex-members still carry roles they should have lost. This walks
every member holding Ex-Member and removes whatever MEMBER_REMOVE_ROLES —
the same list the removal flows now use — still matches. Honored Fish and
Retired Chief are not in that list, so the honorifics are untouched.

Dry-run by default; nothing is written without --apply.

    venv/Scripts/python scripts/cleanup_ex_member_roles.py            # report only
    venv/Scripts/python scripts/cleanup_ex_member_roles.py --apply    # actually strip

Talks straight to the Discord REST API with the prod bot token from .env, so
the bot doesn't need to be running.
"""

import os
import sys
import time
import argparse

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Helpers.member_roles import EX_MEMBER_ROLE, MEMBER_REMOVE_ROLES
from Helpers.variables import PROD_TAQ_GUILD_ID

API = "https://discord.com/api/v10"


def request(session, method, url, **kwargs):
    """One REST call with 429 handling."""
    while True:
        r = session.request(method, url, timeout=30, **kwargs)
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 1)) + 0.2)
            continue
        r.raise_for_status()
        return r


def fetch_all_members(session, guild_id):
    members, after = [], "0"
    while True:
        r = request(session, "GET", f"{API}/guilds/{guild_id}/members",
                    params={"limit": 1000, "after": after})
        batch = r.json()
        if not batch:
            return members
        members.extend(batch)
        after = batch[-1]["user"]["id"]
        if len(batch) < 1000:
            return members


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true",
                        help="actually remove the roles (default: dry-run report)")
    args = parser.parse_args()

    load_dotenv()
    token = os.getenv("TOKEN")
    if not token:
        sys.exit("TOKEN missing from .env (prod bot token)")

    session = requests.Session()
    session.headers.update({"Authorization": f"Bot {token}"})
    guild_id = PROD_TAQ_GUILD_ID

    roles = request(session, "GET", f"{API}/guilds/{guild_id}/roles").json()
    id_by_name = {r["name"]: r["id"] for r in roles}
    name_by_id = {r["id"]: r["name"] for r in roles}

    ex_member_id = id_by_name.get(EX_MEMBER_ROLE)
    if not ex_member_id:
        sys.exit(f"Role {EX_MEMBER_ROLE!r} not found in guild {guild_id}")
    strip_ids = {id_by_name[n] for n in MEMBER_REMOVE_ROLES if n in id_by_name}

    members = fetch_all_members(session, guild_id)
    targets = []
    for m in members:
        if ex_member_id not in m["roles"]:
            continue
        to_strip = [rid for rid in m["roles"] if rid in strip_ids]
        if to_strip:
            targets.append((m, to_strip))

    print(f"members: {len(members)}, ex-members needing cleanup: {len(targets)}")
    for m, to_strip in targets:
        label = m.get("nick") or m["user"].get("global_name") or m["user"]["username"]
        names = ", ".join(sorted(name_by_id[rid] for rid in to_strip))
        print(f"- {label} ({m['user']['id']}): {names}")

    if not args.apply:
        print("\ndry-run: no changes made (re-run with --apply to strip)")
        return

    print("\napplying...")
    for i, (m, to_strip) in enumerate(targets, 1):
        keep = [rid for rid in m["roles"] if rid not in strip_ids]
        request(session, "PATCH", f"{API}/guilds/{guild_id}/members/{m['user']['id']}",
                json={"roles": keep},
                headers={"X-Audit-Log-Reason": "Ex-member guild role cleanup (TAQ-67)"})
        if i % 25 == 0:
            print(f"  {i}/{len(targets)}")
            time.sleep(1.0)
    print(f"done: cleaned {len(targets)} members")


if __name__ == "__main__":
    main()
