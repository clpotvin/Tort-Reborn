"""
Test suite for the discord_links ign rename sync
(Tasks/update_member_data.py UpdateMemberData._sync_member_igns).

The guild loop holds the authoritative {uuid: name} map from the Wynncraft API;
this sync writes name changes back to discord_links, which is otherwise only
written at link time and goes stale forever.

1. A changed name updates the row and reports (old, new)
2. Matching names touch nothing (no UPDATE, no commit)
3. uuid dash-format differences between API and DB still match
4. A uuid with mixed rows (one stale, one current) still converges
5. Members with no discord_links row are ignored
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Tasks import update_member_data as umd


class FakeCursor:
    def __init__(self, stored_rows):
        self.stored_rows = stored_rows
        self.updates = []

    def execute(self, sql, params=None):
        self._is_select = sql.strip().upper().startswith("SELECT")
        if not self._is_select:
            self.updates.append(params)

    def fetchall(self):
        return self.stored_rows


class FakeDB:
    def __init__(self, stored_rows):
        self.cursor = FakeCursor(stored_rows)
        self.connection = self
        self.committed = False
        self.closed = False

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def run_sync(monkeypatch, stored_rows, curr_map):
    db = FakeDB(stored_rows)
    monkeypatch.setattr(umd, "_db_connect_with_retry", lambda: db)
    renames = umd.UpdateMemberData._sync_member_igns(curr_map)
    return db, renames


def test_rename_updates_row(monkeypatch):
    db, renames = run_sync(
        monkeypatch,
        [("110c11c8-d8b7-478d-8adf-b0f606d5f939", "JohnMadDog")],
        {"110c11c8-d8b7-478d-8adf-b0f606d5f939": {"name": "Sedacto", "rank": "Angler"}},
    )
    assert renames == [("JohnMadDog", "Sedacto")]
    assert db.cursor.updates == [("Sedacto", "110c11c8-d8b7-478d-8adf-b0f606d5f939")]
    assert db.committed and db.closed


def test_matching_name_untouched(monkeypatch):
    db, renames = run_sync(
        monkeypatch,
        [("110c11c8-d8b7-478d-8adf-b0f606d5f939", "Sedacto")],
        {"110c11c8-d8b7-478d-8adf-b0f606d5f939": {"name": "Sedacto", "rank": "Angler"}},
    )
    assert renames == []
    assert db.cursor.updates == []
    assert not db.committed


def test_dashless_api_uuid_matches(monkeypatch):
    db, renames = run_sync(
        monkeypatch,
        [("110c11c8-d8b7-478d-8adf-b0f606d5f939", "OldName")],
        {"110c11c8d8b7478d8adfb0f606d5f939": {"name": "NewName", "rank": None}},
    )
    assert renames == [("OldName", "NewName")]


def test_mixed_rows_converge(monkeypatch):
    db, renames = run_sync(
        monkeypatch,
        [
            ("110c11c8-d8b7-478d-8adf-b0f606d5f939", "OldName"),
            ("110c11c8-d8b7-478d-8adf-b0f606d5f939", "NewName"),
        ],
        {"110c11c8-d8b7-478d-8adf-b0f606d5f939": {"name": "NewName", "rank": None}},
    )
    assert renames == [("OldName", "NewName")]
    assert db.cursor.updates == [("NewName", "110c11c8-d8b7-478d-8adf-b0f606d5f939")]


def test_unknown_member_ignored(monkeypatch):
    db, renames = run_sync(
        monkeypatch,
        [("110c11c8-d8b7-478d-8adf-b0f606d5f939", "Sedacto")],
        {"9aeb062a-f769-49bc-8046-4d9c8cc86e5a": {"name": "guywhyII", "rank": None}},
    )
    assert renames == []
    assert db.cursor.updates == []
