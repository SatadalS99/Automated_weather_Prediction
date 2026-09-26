from fastapi import FastAPI, Query, HTTPException

from app.db import query

# ── App setup ──
app = FastAPI(
    title="Weather Anomaly Tracker",
    description=(
        "Detects unusual weather patterns using rolling Z-score statistics. "
        "Data is refreshed daily via a scheduled GitHub Actions ETL pipeline."
    ),
    version="1.0.0",
)


# ── Endpoints ──

@app.get("/", tags=["Info"])
def root():
    """
    Welcome message listing available endpoints.
    """
    return {
        "service": "Weather Anomaly Tracker",
        "endpoints": {
            "GET /health":              "Health check",
            "GET /anomalies":           "Anomaly days (query params: city, days)",
            "GET /weather":             "All weather records (query params: city, days)",
            "GET /docs":                "Interactive API documentation",
        },
    }


@app.get("/health", tags=["Info"])
def health_check():

    return {"status": "ok"}


@app.get("/anomalies", tags=["Weather"])
def get_anomalies(
    city: str = Query(
        default="Dortmund",
        description="City name. One of: Dortmund, Berlin, Munich, Hamburg.",
    ),
    days: int = Query(
        default=7,
        ge=1,
        le=90,
        description="Look back this many days. Must be between 1 and 90.",
    ),
):
    
    rows = query(
        """
        SELECT  date,
                city,
                temp_max,
                temp_min,
                rolling_mean,
                rolling_std,
                z_score,
                anomaly_reason
        FROM    weather_daily
        WHERE   city       = ?
          AND   is_anomaly = 1
          AND   date      >= date('now', ? || ' days')
        ORDER   BY date DESC
        """,
        (city, f"-{days}"),
    )

    return {
        "city":          city,
        "days_checked":  days,
        "anomaly_count": len(rows),
        "anomalies":     rows,
    }


@app.get("/weather", tags=["Weather"])
def get_weather(
    city: str = Query(
        default="Dortmund",
        description="City name.",
    ),
    days: int = Query(
        default=7,
        ge=1,
        le=90,
        description="Number of past days to return.",
    ),
):
    
    rows = query(
        """
        SELECT  date,
                city,
                temp_max,
                temp_min,
                precipitation,
                rolling_mean,
                rolling_std,
                z_score,
                is_anomaly
        FROM    weather_daily
        WHERE   city = ?
          AND   date >= date('now', ? || ' days')
        ORDER   BY date DESC
        """,
        (city, f"-{days}"),
    )

    # Return a helpful error if there's no data for this city yet
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No data found for '{city}' in the last {days} days. "
                "Has the ETL pipeline run yet? Try: python -m etl.run_pipeline"
            ),
        )

    return {
        "city":    city,
        "days":    days,
        "records": rows,
    }
