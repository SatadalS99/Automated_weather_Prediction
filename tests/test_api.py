import os
import sqlite3
import tempfile
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

# ── Point to a temp DB BEFORE importing app modules──
# This must happen before "from app.main import app" because app/db.py reads
# DB_PATH at import time. Setting it here ensures the test uses the temp file.
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DB_PATH"] = _tmp_db.name

from app.main import app   # noqa: E402 — import after env var is set

client = TestClient(app)


# ── Database seeding ──
# Use RECENT dates so they fall within the API's max look-back window (90 days).

def _d(days_ago: int) -> str:
    """Return a date string N days before today."""
    return (date.today() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _make_sample_rows():
    return [
        # (date, city, temp_max, temp_min, precip, mean, std, z_score, is_anomaly, reason, loaded_at)
        (_d(5), "Dortmund", 22.0, 14.0, 0.0,  20.0, 2.0,  1.0,  0, "",                                                                    "2024-06-01T08:00:00Z"),
        (_d(4), "Dortmund", 38.0, 26.0, 0.0,  20.0, 2.0,  9.0,  1, "Temp 38.0°C is 9.0 std deviations above the 20.0°C rolling average",  "2024-06-02T08:00:00Z"),
        (_d(3), "Dortmund", 19.5, 12.0, 3.2,  20.0, 2.0, -0.25, 0, "",                                                                    "2024-06-03T08:00:00Z"),
        (_d(5), "Berlin",   18.0, 10.0, 1.1,  17.0, 1.5,  0.67, 0, "",                                                                    "2024-06-01T08:00:00Z"),
    ]

ANOMALY_DATE   = _d(4)   # the date we seeded as an anomaly
NORMAL_DATE    = _d(5)   # a normal day

CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS weather_daily (
        date TEXT, city TEXT, temp_max REAL, temp_min REAL,
        precipitation REAL, rolling_mean REAL, rolling_std REAL,
        z_score REAL, is_anomaly INTEGER DEFAULT 0,
        anomaly_reason TEXT DEFAULT '', loaded_at TEXT,
        PRIMARY KEY (date, city)
    )
"""

INSERT_SQL = """
    INSERT OR IGNORE INTO weather_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)
"""


def seed_database() -> None:
    """Insert sample rows into the test database."""
    conn = sqlite3.connect(_tmp_db.name)
    conn.execute(CREATE_SQL)
    conn.executemany(INSERT_SQL, _make_sample_rows())
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def setup_and_teardown():    
    seed_database()
    yield   # test runs here
    # (cleanup could go here if needed)


# ── Health endpoint tests ──

class TestHealthEndpoint:

    def test_returns_200(self):        
        response = client.get("/health")
        assert response.status_code == 200

    def test_returns_ok_status(self):        
        data = client.get("/health").json()
        assert data == {"status": "ok"}


# ── Root endpoint tests ──

class TestRootEndpoint:

    def test_returns_200(self):
        response = client.get("/")
        assert response.status_code == 200

    def test_lists_endpoints(self):
        data = client.get("/").json()
        assert "endpoints" in data
        assert "GET /anomalies" in data["endpoints"]
        assert "GET /weather" in data["endpoints"]


# ── /anomalies endpoint tests ──

class TestAnomaliesEndpoint:

    def test_returns_200(self):
        response = client.get("/anomalies?city=Dortmund&days=30")
        assert response.status_code == 200

    def test_response_has_required_keys(self):        
        data = client.get("/anomalies?city=Dortmund&days=30").json()
        assert "city"          in data
        assert "days_checked"  in data
        assert "anomaly_count" in data
        assert "anomalies"     in data

    def test_anomalies_is_a_list(self):
        data = client.get("/anomalies?city=Dortmund&days=30").json()
        assert isinstance(data["anomalies"], list)

    def test_finds_seeded_anomaly(self):        
        data = client.get("/anomalies?city=Dortmund&days=30").json()
        dates = [row["date"] for row in data["anomalies"]]
        assert ANOMALY_DATE in dates, \
            f"Expected {ANOMALY_DATE} in anomalies, got: {dates}"

    def test_normal_day_not_in_anomalies(self):        
        data = client.get("/anomalies?city=Dortmund&days=30").json()
        dates = [row["date"] for row in data["anomalies"]]
        assert NORMAL_DATE not in dates

    def test_anomaly_count_matches_list_length(self):       
        data = client.get("/anomalies?city=Dortmund&days=30").json()
        assert data["anomaly_count"] == len(data["anomalies"])

    def test_city_filter_works(self):        
        data = client.get("/anomalies?city=Berlin&days=30").json()
        assert data["city"] == "Berlin"
        for row in data["anomalies"]:
            assert row["city"] == "Berlin"

    def test_days_validation_too_high(self):        
        response = client.get("/anomalies?days=9999999")
        assert response.status_code == 422

    def test_days_validation_too_low(self):        
        response = client.get("/anomalies?days=0")
        assert response.status_code == 422

    def test_default_city_is_dortmund(self):       
        data = client.get("/anomalies").json()
        assert data["city"] == "Dortmund"


# ── /weather endpoint tests ──

class TestWeatherEndpoint:

    def test_returns_200_for_dortmund(self):
        response = client.get("/weather?city=Dortmund&days=30")
        assert response.status_code == 200

    def test_returns_all_seeded_rows_for_dortmund(self):        
        data = client.get("/weather?city=Dortmund&days=30").json()
        assert len(data["records"]) == 3

    def test_response_has_required_keys(self):
        data = client.get("/weather?city=Dortmund&days=30").json()
        assert "city" in data
        assert "days" in data
        assert "records" in data

    def test_records_include_both_anomaly_and_normal(self):        
        data = client.get("/weather?city=Dortmund&days=30").json()
        anomaly_flags = [row["is_anomaly"] for row in data["records"]]
        assert 0 in anomaly_flags, "Normal days should be in /weather results"
        assert 1 in anomaly_flags, "Anomaly days should be in /weather results"

    def test_unknown_city_returns_404(self):        
        response = client.get("/weather?city=NonExistentCity123")
        assert response.status_code == 404

    def test_404_message_is_helpful(self):        
        response = client.get("/weather?city=NonExistentCity123")
        detail = response.json().get("detail", "")
        assert "ETL" in detail or "pipeline" in detail.lower(), \
           
