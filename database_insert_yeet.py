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

    discord_id = '170719819715313665'
    ign        = 'Thundderr'
    uuid       = 'ea7ca108-8e11-4a4e-9cd6-03d1c5cd2484'
    linked     = True
    rank       = 'Sailfish'
    wars_on_join = 0

    shell_user = discord_id
    shells_amt = 50
    balance_amt = 20

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
            discord_id,
            ign,
            uuid,
            linked,
            rank,
            wars_on_join
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
            shell_user,
            shells_amt,
            balance_amt
        ))

        # Commit transaction
        conn.commit()
        print("Rows inserted successfully.")

        # Now fetch & print to verify

        print("\n-- discord_links row:")
        cur.execute("""
            SELECT discord_id, ign, uuid, linked, rank, wars_on_join
              FROM discord_links
             WHERE discord_id = %s;
        """, (discord_id,))
        row = cur.fetchone()
        if row:
            print("discord_links:", row)
        else:
            print("No row found in discord_links for", discord_id)

        print("\n-- shells row:")
        cur.execute("""
            SELECT "user", shells, balance
              FROM shells
             WHERE "user" = %s;
        """, (shell_user,))
        row = cur.fetchone()
        if row:
            print("shells:", row)
        else:
            print("No row found in shells for", shell_user)

    except Exception as e:
        conn.rollback()
        print("Error inserting or fetching rows:", e)

    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
