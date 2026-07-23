from Helpers.database import DB


def ensure_panel_tables():
    db = DB()
    try:
        db.connect()
        db.cursor.execute("""
            CREATE TABLE IF NOT EXISTS info_panels (
              id                SERIAL PRIMARY KEY,
              name              TEXT NOT NULL,
              channel_id        BIGINT,
              message_id        BIGINT,
              draft             JSONB NOT NULL DEFAULT '[]'::jsonb,
              published         JSONB NOT NULL DEFAULT '[]'::jsonb,
              sync_state        TEXT NOT NULL DEFAULT 'idle',
              last_published_at TIMESTAMPTZ,
              last_published_by TEXT,
              last_error        TEXT,
              created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        db.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_info_panels_sync_state ON info_panels (sync_state)"
        )
        db.cursor.execute("""
            CREATE TABLE IF NOT EXISTS discord_channels (
              channel_id BIGINT PRIMARY KEY,
              name       TEXT NOT NULL,
              category   TEXT,
              position   INTEGER NOT NULL DEFAULT 0,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        db.connection.commit()
    finally:
        db.close()


def claim_panels(state):
    db = DB()
    try:
        db.connect()
        db.cursor.execute(
            "SELECT id, name, channel_id, message_id, published "
            "FROM info_panels WHERE sync_state = %s",
            (state,),
        )
        return db.cursor.fetchall()
    finally:
        db.close()


def mark_published(panel_id, message_id):
    db = DB()
    try:
        db.connect()
        db.cursor.execute(
            "UPDATE info_panels SET message_id = %s, sync_state = 'idle', "
            "last_published_at = now(), last_error = NULL, updated_at = now() "
            "WHERE id = %s",
            (message_id, panel_id),
        )
        db.connection.commit()
    finally:
        db.close()


def mark_error(panel_id, message):
    db = DB()
    try:
        db.connect()
        db.cursor.execute(
            "UPDATE info_panels SET last_error = %s, updated_at = now() WHERE id = %s",
            (message[:500], panel_id),
        )
        db.connection.commit()
    finally:
        db.close()


def delete_panel_row(panel_id):
    db = DB()
    try:
        db.connect()
        db.cursor.execute("DELETE FROM info_panels WHERE id = %s", (panel_id,))
        db.connection.commit()
    finally:
        db.close()


def upsert_channels(rows):
    db = DB()
    try:
        db.connect()
        for channel_id, name, category, position in rows:
            db.cursor.execute(
                "INSERT INTO discord_channels (channel_id, name, category, position, updated_at) "
                "VALUES (%s, %s, %s, %s, now()) "
                "ON CONFLICT (channel_id) DO UPDATE SET "
                "name = EXCLUDED.name, category = EXCLUDED.category, "
                "position = EXCLUDED.position, updated_at = now()",
                (channel_id, name, category, position),
            )
        db.connection.commit()
    finally:
        db.close()


def prune_channels(keep_ids):
    db = DB()
    try:
        db.connect()
        if keep_ids:
            db.cursor.execute(
                "DELETE FROM discord_channels WHERE channel_id <> ALL(%s)",
                (list(keep_ids),),
            )
        else:
            db.cursor.execute("DELETE FROM discord_channels")
        db.connection.commit()
    finally:
        db.close()
