import os
import sqlite3
from datetime import datetime, timezone

import pandas as pd


# Path to the SQLite database file.
# Override this with the DB_PATH environment variable in production.
DB_PATH: str = os.getenv("DB_PATH", "data/weather.db")

# SQL for creating the table. We run this every time — it's safe because
# of the "IF NOT EXISTS" clause: existing tables are never touched.
CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS weather_daily (
        date            TEXT    NOT NULL,
        city            TEXT    NOT NULL,
        temp_max        REAL,
        temp_min        REAL,
        precipitation   REAL,
        rolling_mean    REAL,
        rolling_std     REAL,
        z_score         REAL,
        is_anomaly      INTEGER DEFAULT 0,
        anomaly_reason  TEXT    DEFAULT '',
        loaded_at       TEXT,
        PRIMARY KEY (date, city)   -- enforces uniqueness: one row per city per day
    )
"""

# We insert with OR IGNORE so duplicate rows are silently skipped.
INSERT_SQL = """
    INSERT OR IGNORE INTO weather_daily
        (date, city, temp_max, temp_min, precipitation,
         rolling_mean, rolling_std, z_score,
         is_anomaly, anomaly_reason, loaded_at)
    VALUES
        (:date, :city, :temp_max, :temp_min, :precipitation,
         :rolling_mean, :rolling_std, :z_score,
         :is_anomaly, :anomaly_reason, :loaded_at)
"""


def get_connection() -> sqlite3.Connection:    
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def load(df: pd.DataFrame) -> int:    
    conn = get_connection()

    # Create the table if this is the first ever run
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()

    # Count existing rows so we can report how many are new
    row_count_before = conn.execute(
        "SELECT COUNT(*) FROM weather_daily"
    ).fetchone()[0]

    # ── Prepare the DataFrame for insertion ──
    df = df.copy()

    # Convert datetime objects to "YYYY-MM-DD" strings for SQLite TEXT storage
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    # Record when this pipeline run happened (UTC timestamp)
    df["loaded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Fill NaN values so SQLite doesn't complain about None in numeric columns
    df["rolling_mean"]   = df["rolling_mean"].fillna(0.0)
    df["rolling_std"]    = df["rolling_std"].fillna(0.0)
    df["z_score"]        = df["z_score"].fillna(0.0)
    df["anomaly_reason"] = df["anomaly_reason"].fillna("")

    # Select only the columns we need (drop any extras from transform)
    columns = [
        "date", "city", "temp_max", "temp_min", "precipitation",
        "rolling_mean", "rolling_std", "z_score",
        "is_anomaly", "anomaly_reason", "loaded_at",
    ]
    records = df[columns].to_dict(orient="records")

    # Insert all rows in a single transaction.
    # executemany() is much faster than a loop of execute() calls.
    conn.executemany(INSERT_SQL, records)
    conn.commit()

    # Count rows after insert to see how many were new
    row_count_after = conn.execute(
        "SELECT COUNT(*) FROM weather_daily"
    ).fetchone()[0]
    conn.close()

    new_rows = row_count_after - row_count_before
    print(
        f"[Load] Inserted {new_rows} new rows. "
        f"Total rows in DB: {row_count_after}."
    )
    return new_rows


def query_anomalies(city: str, days: int = 7) -> list[dict]:

    conn = get_connection()
    conn.row_factory = sqlite3.Row   # makes rows behave like dicts

    rows = conn.execute(
        """
        SELECT date, city, temp_max, rolling_mean, rolling_std,
               z_score, anomaly_reason
        FROM   weather_daily
        WHERE  city       = ?
          AND  is_anomaly = 1
          AND  date       >= date('now', ? || ' days')
        ORDER  BY date DESC
        """,
        (city, f"-{days}"),
    ).fetchall()

    conn.close()
    return [dict(row) for row in rows]


# ── Quick manual test ──
# Run this file directly to execute the full pipeline and inspect the DB:
#   python -m etl.load
if __name__ == "__main__":
    from etl.extract import fetch_weather
    from etl.transform import run as transform_data

    raw         = fetch_weather("Dortmund")
    transformed = transform_data(raw)
    load(transformed)

    print("\n--- Anomalies in DB (last 30 days) ---")
    anomalies = query_anomalies("Dortmund", days=30)
    if not anomalies:
        print("No anomalies stored yet.")
    else:
        for row in anomalies:
            print(f"  {row['date']} | {row['temp_max']}°C | {row['anomaly_reason']}")
