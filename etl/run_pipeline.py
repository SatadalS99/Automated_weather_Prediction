import sys

from etl.extract import fetch_weather
from etl.transform import run as transform
from etl.load import load
from alerts.notify import notify_anomalies

# Default cities to process on every run
CITIES = ["Dortmund", "Berlin", "Munich"]


def run_pipeline(city: str) -> None:
    """
    Run the full ETL pipeline for one city.

    Args:
        city: Must be in the CITIES dict in etl/extract.py

    Raises:
        Any exception from extract/transform/load will propagate up,
        causing the GitHub Actions job to fail and notify you.
    """
    print(f"\n{'=' * 52}")
    print(f"  Processing: {city}")
    print(f"{'=' * 52}")

    # ── Step 1: Extract ───────────────────────────────────────
    raw_df = fetch_weather(city, past_days=30)

    # ── Step 2: Transform ─────────────────────────────────────
    transformed_df = transform(raw_df)

    # ── Step 3: Load ──────────────────────────────────────────
    load(transformed_df)

    # ── Step 4: Alert ─────────────────────────────────────────
    # Only alert for TODAY's row, not historical anomalies
    # (we don't want to spam alerts for old data every time the pipeline runs)
    today = transformed_df["date"].max()
    today_rows = transformed_df[
        (transformed_df["date"] == today) &
        (transformed_df["is_anomaly"] == 1)
    ]

    if not today_rows.empty:
        # Convert to plain dicts for the notify function
        anomaly_records = (
            today_rows[["date", "temp_max", "anomaly_reason"]]
            .assign(date=lambda df: df["date"].dt.strftime("%Y-%m-%d"))
            .to_dict(orient="records")
        )
        notify_anomalies(anomaly_records, city)
    else:
        print(f"[Pipeline] No anomaly today for {city} — no alert sent.")


def main() -> int:
    """
    Entry point. Returns 0 on full success, 1 if any city failed.
    """
    # Allow overriding cities from command line
    cities = sys.argv[1:] if len(sys.argv) > 1 else CITIES

    failed = []
    for city in cities:
        try:
            run_pipeline(city)
        except Exception as exc:
            print(f"\n[Pipeline] ERROR processing {city}: {exc}")
            failed.append(city)

    if failed:
        print(f"\n[Pipeline] Failed cities: {failed}")
        return 1

    print(f"\n[Pipeline] All done. Cities processed: {cities}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
