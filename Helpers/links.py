"""Guards for discord_links writes.

A Minecraft account may be linked to at most one Discord account at a time.
The database enforces this with the partial unique index
discord_links_linked_uuid_uq (schema.sql); duplicate linked rows fan out every
uuid join in the bot and website, duplicating leaderboard rows and
double-counting raid points. These helpers let write paths detect the conflict
up front and report it to the invoker instead of failing on the constraint.

Unlinked historical rows (e.g. a member who left) may still share a uuid with
a live link — only currently-linked rows are protected.
"""


class LinkConflictError(Exception):
    """Raised when a uuid is already linked to a different Discord account."""

    def __init__(self, uuid, other_discord_id, other_ign):
        self.uuid = uuid
        self.other_discord_id = other_discord_id
        self.other_ign = other_ign
        super().__init__(
            f"Minecraft account {other_ign} ({uuid}) is already linked to "
            f"Discord account {other_discord_id}"
        )

    def user_message(self):
        """Standard operator-facing explanation for command responses."""
        return (
            f":no_entry: **{self.other_ign}** is already linked to "
            f"<@{self.other_discord_id}>. Unlink that account first "
            f"(or remove the stale row) before linking it elsewhere."
        )


def find_linked_uuid_conflict(cursor, uuid, discord_id):
    """Return (discord_id, ign) of a *different* Discord account currently
    linked to this uuid, or None."""
    if not uuid:
        return None
    cursor.execute(
        "SELECT discord_id, ign FROM discord_links"
        " WHERE uuid = %s AND linked = TRUE AND discord_id <> %s"
        " LIMIT 1",
        (uuid, discord_id),
    )
    return cursor.fetchone()


def assert_uuid_free(cursor, uuid, discord_id):
    """Raise LinkConflictError if uuid is linked to a different Discord account."""
    conflict = find_linked_uuid_conflict(cursor, uuid, discord_id)
    if conflict:
        raise LinkConflictError(uuid, conflict[0], conflict[1])


def assert_row_linkable(cursor, discord_id):
    """Guard for paths that flip an existing row to linked = TRUE without
    touching its uuid: raise LinkConflictError if that row's uuid is already
    linked to a different Discord account."""
    cursor.execute(
        "SELECT uuid FROM discord_links WHERE discord_id = %s",
        (discord_id,),
    )
    row = cursor.fetchone()
    if row and row[0]:
        assert_uuid_free(cursor, row[0], discord_id)
