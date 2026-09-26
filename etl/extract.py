import requests
import pandas as pd


# ── City registry ──
# Add more cities here — just look up lat/lon on https://open-meteo.com
CITIES: dict[str, dict[str, float]] = {
    "Dortmund": {"latitude": 51.514, "longitude": 7.468},
    "Berlin":   {"latitude": 52.520, "longitude": 13.405},
    "Munich":   {"latitude": 48.137, "longitude": 11.576},
    "Hamburg":  {"latitude": 53.551, "longitude": 9.994},
}


def fetch_weather(city: str = "Dortmund", past_days: int = 30) -> pd.DataFrame:

    if city not in CITIES:
        raise ValueError(
            f"Unknown city '{city}'. "
            f"Available cities: {list(CITIES.keys())}"
        )

    coords = CITIES[city]

    # Build the API URL and query parameters
    # Open-Meteo returns each variable as a separate list, all same length
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude":      coords["latitude"],
        "longitude":     coords["longitude"],
        "daily":         "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "past_days":     past_days,
        "forecast_days": 1,          # also include today
        "timezone":      "Europe/Berlin",
    }

    print(f"[Extract] Fetching {past_days} days of weather for {city}...")

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()      # raises an exception if status code != 200

    data = response.json()           # parse JSON response

    # The API returns parallel lists under data["daily"]
    # e.g. {"time": ["2024-01-01", ...], "temperature_2m_max": [5.2, ...], ...}
    # We zip them together into a DataFrame — one row per day
    daily = data["daily"]
    df = pd.DataFrame({
        "date":          daily["time"],
        "city":          city,
        "temp_max":      daily["temperature_2m_max"],
        "temp_min":      daily["temperature_2m_min"],
        "precipitation": daily["precipitation_sum"],
    })

    # Convert date strings ("2024-01-01") to proper datetime objects
    df["date"] = pd.to_datetime(df["date"])

    # Drop rows where the API returned null for all weather values
    # (can happen for future forecast days that haven't been measured yet)
    df = df.dropna(subset=["temp_max", "temp_min"])

    print(f"[Extract] Done — {len(df)} days downloaded.")
    return df


# ── Quick manual test ──

if __name__ == "__main__":
    df = fetch_weather("Dortmund")
    print("\nFirst 3 rows:")
    print(df.head(3).to_string())
    print("\nLast 3 rows (most recent):")
    print(df.tail(3).to_string())
    print(f"\nShape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
