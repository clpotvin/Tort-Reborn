"""
Regression tests for /background set (Commands/background.py).

The `owned` column of profile_customization is JSONB NOT NULL with no default,
so the upsert that saves a user's active background MUST provide `owned` on the
INSERT — otherwise a first-time insert (no existing row) fails with
psycopg2.errors.NotNullViolation and the command reports a spurious failure even
though nothing about the chosen background is wrong.
"""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Commands.background import Background

_set_background = Background.__dict__["set_background"].callback


def _run_set(background_name, backgrounds_row, owned_row):
    """Invoke set_background with a fully mocked DB, returning the DB cursor.

    backgrounds_row: what `SELECT * FROM profile_backgrounds` returns.
    owned_row:       what `SELECT owned FROM profile_customization` returns
                     (None simulates a first-time user with no row yet).
    """
    cursor = MagicMock()
    cursor.fetchone.side_effect = [backgrounds_row, owned_row]

    db = MagicMock()
    db.cursor = cursor

    message = MagicMock()
    message.defer = AsyncMock()
    message.respond = AsyncMock()
    message.author.id = 924263676112932935

    cog = Background(MagicMock())

    with patch("Commands.background.DB", return_value=db), patch(
        "Commands.background.get_background_file", return_value=MagicMock()
    ):
        asyncio.run(_set_background(cog, message, background=background_name))

    return cursor, message


def _find_customization_insert(cursor):
    for call in cursor.execute.call_args_list:
        sql = call.args[0]
        if "INSERT INTO profile_customization" in sql:
            return sql, (call.args[1] if len(call.args) > 1 else ())
    return None, None


def test_first_time_user_insert_provides_owned():
    # New user (no row) sets the Default background (id 0, always owned).
    # This is the exact path that hit the NOT NULL violation in production.
    cursor, message = _run_set(
        "Default",
        backgrounds_row=(0, "Default", True, 0, ""),
        owned_row=None,
    )

    sql, params = _find_customization_insert(cursor)
    assert sql is not None, "set_background never inserted a customization row"
    assert '"owned"' in sql or "owned" in sql, "INSERT omits the NOT NULL `owned` column"
    # owned must be supplied and non-null so a fresh insert satisfies the constraint.
    assert len(params) == 3, f"expected (user, background, owned) params, got {params!r}"
    assert params[2] is not None
    json.loads(params[2])  # must be valid JSON for the JSONB column
    message.respond.assert_awaited()  # command completed instead of raising


def test_existing_owner_upsert_provides_owned():
    # Existing owner re-setting an owned background still supplies owned so the
    # statement is valid whether it inserts or updates.
    cursor, _ = _run_set(
        "Shrooms",
        backgrounds_row=(12, "Shrooms", True, 50, "mushrooms"),
        owned_row=([12],),
    )

    sql, params = _find_customization_insert(cursor)
    assert sql is not None
    assert "owned" in sql
    assert len(params) == 3 and params[2] is not None
