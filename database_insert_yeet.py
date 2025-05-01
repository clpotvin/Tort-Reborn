#!/usr/bin/env python3
import psycopg2

def main():
    # Connection parameters
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="tortreborn",
        user="tortuser",
        password="UserPass123"
    )
    cur = conn.cursor()

    try:
        # Begin transaction
        cur.execute("BEGIN;")

        # Insert into discord_links
        cur.execute("""
            INSERT INTO discord_links (
                discord_id,
                ign,
                uuid,
                linked,
                rank,
                wars_on_join
            ) VALUES (
                %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (discord_id) DO NOTHING;
        """, (
            '170719819715313665',
            'Thundderr',
            'ea7ca108-8e11-4a4e-9cd6-03d1c5cd2484',
            True,
            'Sailfish',
            0
        ))

        # Insert into shells
        cur.execute("""
            INSERT INTO shells (
                "user",
                shells,
                balance
            ) VALUES (
                %s, %s, %s
            )
            ON CONFLICT ("user") DO NOTHING;
        """, (
            '170719819715313665',
            50,
            20
        ))

        # Commit transaction
        conn.commit()
        print("Rows inserted successfully.")

    except Exception as e:
        conn.rollback()
        print("Error inserting rows:", e)

    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
