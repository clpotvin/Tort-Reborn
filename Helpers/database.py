import os

import mariadb


class DB:
    def __init__(self):
        self.connection = None
        self.cursor = None

    def connect(self):
        try:
            self.connection = mariadb.connect(
                user=os.getenv("DB_LOGIN"),
                password=os.getenv("DB_PASS"),
                host=os.getenv("DB_HOST"),
                port=int(os.getenv("DB_PORT")),
                database=os.getenv("DB_DATABASE")
            )
        except mariadb.Error as e:
            print(f"Error connecting to MariaDB Platform: {e}")

        self.cursor = self.connection.cursor()

    def close(self):
        self.connection.close()
