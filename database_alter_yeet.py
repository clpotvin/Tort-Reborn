#!/usr/bin/env python3
import psycopg2

def main():
    # Connection parameters (same as before)
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="tortreborn",
        user="tortuser",
        password="UserPass123"
    )
    cur = conn.cursor()

    try:
        # Begin a transaction
        cur.execute("BEGIN;")

        # 1) Drop the unique constraint on channel
        cur.execute("""
            ALTER TABLE new_app
            DROP CONSTRAINT IF EXISTS new_app_channel_key;
        """)

        # 2) (Optional) If you had an index enforcing uniqueness you can drop it too:
        # cur.execute("DROP INDEX IF EXISTS new_app_channel_idx;")

        # Commit the change
        conn.commit()
        print("Dropped unique constraint on new_app.channel successfully.")

    except Exception as e:
        conn.rollback()
        print("Error altering table:", e)

    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
