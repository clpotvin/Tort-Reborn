import os
import psycopg2
from psycopg2 import OperationalError

class DB:
    def __init__(self):
        self.connection = None
        self.cursor = None

    def connect(self):
        try:
            self.connection = psycopg2.connect(
                user=os.getenv("DB_LOGIN"),
                password=os.getenv("DB_PASS"),
                host=os.getenv("DB_HOST"),
                port=int(os.getenv("DB_PORT")),
                database=os.getenv("DB_DATABASE", "postgres"),
                sslmode=os.getenv("DB_SSLMODE")
            )
            self.cursor = self.connection.cursor()
        except OperationalError as e:
            print(f"[DB] Connection failed: {e}")
            raise

    def close(self):
        """Close cursor and connection."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
