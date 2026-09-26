import pandas as pd

# How many standard deviations away = anomaly
# 2.0 is a good starting point. Increase to 2.5 or 3.0 to reduce noise.
SIGMA_THRESHOLD: float = 2.0

# Rolling window size in days
ROLLING_WINDOW: int = 30


def add_rolling_stats(df: pd.DataFrame, window: int = ROLLING_WINDOW) -> pd.DataFrame:

    # Sort chronologically — rolling windows require correct order
    df = df.sort_values("date").reset_index(drop=True)

    # min_periods=7 means we need at least 7 days of history to compute stats.
    # For the very first few rows (days 1-6), the stats will be NaN.
    df["rolling_mean"] = (
        df["temp_max"]
        .rolling(window=window, min_periods=7)
        .mean()
        .round(2)
    )
    df["rolling_std"] = (
        df["temp_max"]
        .rolling(window=window, min_periods=7)
        .std()
        .round(2)
    )

    return df


def flag_anomalies(
    df: pd.DataFrame,
    sigma_threshold: float = SIGMA_THRESHOLD,
) -> pd.DataFrame:

    df = df.copy()

    # Compute Z-score.
    # Where rolling_std is 0 or NaN, Z-score will be NaN — we handle that below.
    df["z_score"] = (
        (df["temp_max"] - df["rolling_mean"]) / df["rolling_std"]
    ).round(2)

    # Flag rows where the absolute Z-score exceeds the threshold.
    # fillna(0) treats NaN Z-scores (first few rows) as normal days.
    df["is_anomaly"] = (
        df["z_score"].abs().fillna(0) > sigma_threshold
    ).astype(int)

    # Build a human-readable reason string for anomalous days
    df["anomaly_reason"] = df.apply(_build_reason, axis=1)

    n_anomalies = int(df["is_anomaly"].sum())
    print(
        f"[Transform] Flagged {n_anomalies} anomaly/anomalies "
        f"out of {len(df)} days (threshold: ±{sigma_threshold}σ)."
    )

    return df


def _build_reason(row: pd.Series) -> str:
    
    if row["is_anomaly"] == 0:
        return ""

    direction = "above" if row["z_score"] > 0 else "below"
    mean_str  = f"{row['rolling_mean']:.1f}" if pd.notna(row["rolling_mean"]) else "?"
    z_str     = f"{abs(row['z_score']):.1f}"

    return (
        f"Temp {row['temp_max']}°C is {z_str} std deviations {direction} "
        f"the {mean_str}°C rolling average"
    )


def run(df: pd.DataFrame) -> pd.DataFrame:
    
    df = add_rolling_stats(df)
    df = flag_anomalies(df)
    return df


# ── Quick manual test ─────────────────────────────────────────────────────────
# Run this file directly:
#   python -m etl.transform
if __name__ == "__main__":
    from etl.extract import fetch_weather

    raw = fetch_weather("Dortmund")
    result = run(raw)

    print("\n--- All data (last 5 rows) ---")
    cols = ["date", "temp_max", "rolling_mean", "rolling_std", "z_score", "is_anomaly"]
    print(result[cols].tail(5).to_string(index=False))

    anomalies = result[result["is_anomaly"] == 1]
    print(f"\n--- Anomalies found ({len(anomalies)}) ---")
    if anomalies.empty:
        print("No anomalies detected. (Try a lower SIGMA_THRESHOLD to see flagged rows.)")
    else:
        print(anomalies[["date", "temp_max", "anomaly_reason"]].to_string(index=False))
