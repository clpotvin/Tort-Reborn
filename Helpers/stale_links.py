from Helpers.variables import discord_ranks


def uuid_key(value):
    if not value:
        return None
    return str(value).replace("-", "").lower()


def stale_taq_links(rows, guild_members, discord_member_ids=None):
    guild_uuids = {
        key for key in (uuid_key(member.get("uuid")) for member in guild_members)
        if key
    }
    member_ids = {int(user_id) for user_id in discord_member_ids} if discord_member_ids is not None else None
    rank_order = {rank: index for index, rank in enumerate(discord_ranks)}
    stale = []

    for discord_id, ign, uuid, rank, *flags in rows:
        if rank not in discord_ranks:
            continue
        if uuid_key(uuid) in guild_uuids:
            continue
        if member_ids is not None and int(discord_id) not in member_ids:
            continue
        stale.append({
            "discord_id": int(discord_id),
            "ign": ign or "Unknown",
            "uuid": str(uuid),
            "rank": rank,
            "was_honored_fish": bool(flags[0]) if len(flags) > 0 else False,
            "was_retired_chief": bool(flags[1]) if len(flags) > 1 else False,
        })

    return sorted(stale, key=lambda row: (rank_order[row["rank"]], row["ign"].lower(), row["discord_id"]))


def render_stale_taq_links(rows):
    if not rows:
        return "No stale linked members found."
    lines = [f"Found {len(rows)} stale linked member(s):"]
    lines += [
        f"{row['ign']} | {row['rank']} | Discord: {row['discord_id']} | UUID: {row['uuid']}"
        for row in rows
    ]
    return "\n".join(lines)


def split_stale_report(text, limit=1900):
    chunks = []
    current = []
    size = 0
    for line in text.splitlines():
        line_size = len(line) + 1
        if current and size + line_size > limit:
            chunks.append("\n".join(current))
            current = []
            size = 0
        current.append(line)
        size += line_size
    if current:
        chunks.append("\n".join(current))
    return chunks
