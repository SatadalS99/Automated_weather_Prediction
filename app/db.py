import os
import sqlite3

# Read DB path from environment variable, default to local file
DB_PATH: str = os.getenv("DB_PATH", "data/weather.db")


def get_connection() -> sqlite3.Connection:

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql: str, params: tuple = ()) -> list[dict]:

    conn = get_connection()
    try:
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()   # always close, even if an exception occurred
