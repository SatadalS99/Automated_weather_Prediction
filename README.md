# Weather Anomaly Tracker

A production-style data pipeline that detects unusual weather patterns using
rolling Z-score statistics. Built with Python, FastAPI, SQLite, and GitHub Actions.

**What it does every morning at 08:00:**
1. Downloads the last 30 days of weather data from the free Open-Meteo API
2. Computes a rolling mean and standard deviation for each city
3. Flags days where the temperature is more than 2 standard deviations from the average
4. Stores the results in a database
5. Sends an alert via Telegram or email if today is an anomaly

**What you can query at any time:**
```
GET /anomalies?city=Dortmund&days=14   → recent anomaly days
GET /weather?city=Dortmund&days=30     → all weather records
GET /health                            → health check
GET /docs                              → interactive API documentation
```

---

## Project Structure

```
weather-anomaly-tracker/
│
├── .github/
│   └── workflows/
│       ├── ci.yml          ← runs tests + deploys on every push to main
│       └── etl.yml         ← runs the ETL pipeline daily at 08:00 UTC
│
├── etl/                    ← the data pipeline (Extract → Transform → Load)
│   ├── extract.py          ← calls Open-Meteo API, returns a DataFrame
│   ├── transform.py        ← computes rolling stats, flags anomalies
│   ├── load.py             ← writes to SQLite database
│   └── run_pipeline.py     ← orchestrates steps 1-3, then sends alerts
│
├── app/                    ← the FastAPI web service
│   ├── main.py             ← API endpoints (/anomalies, /weather, /health)
│   └── db.py               ← database query helper
│
├── alerts/
│   └── notify.py           ← Telegram and email alert dispatcher
│
├── tests/
│   ├── test_transform.py   ← unit tests for anomaly detection logic
│   └── test_api.py         ← integration tests for API endpoints
│
├── data/
│   └── weather.db          ← SQLite database (created on first run, gitignored)
│
├── .env.example            ← template for local environment variables
├── render.yaml             ← deployment config for Render.com
└── requirements.txt
```

---

## How It Works

### The ETL Pipeline

```
Open-Meteo API
      │
      ▼
  [Extract]   fetch_weather()
  Downloads 30 days of temp_max, temp_min, precipitation
  for each city as a pandas DataFrame
      │
      ▼
  [Transform] run()
  Adds rolling_mean and rolling_std (30-day window).
  Flags a day as anomaly if |Z-score| > 2.0
  Z-score = (temp_max - rolling_mean) / rolling_std
      │
      ├──── if today is anomaly ──→  [Alert]  send_telegram() / send_email()
      │
      ▼
  [Load]   load()
  Writes enriched rows to SQLite using INSERT OR IGNORE
  (idempotent — safe to run twice)
```

### Why Rolling Statistics?

A fixed threshold like "flag anything above 30°C" fails in Germany because
30°C in July is normal, but in March it would be extraordinary.

Rolling statistics adapt automatically to the season:
- In winter: rolling mean ≈ 3°C → flags a 9°C day as unusual
- In summer: rolling mean ≈ 22°C → only flags truly extreme days (35°C+)

---

## Setup — Local Development

### Prerequisites
- Python 3.11+
- Git

### Step 1: Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/weather-anomaly-tracker.git
cd weather-anomaly-tracker

python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### Step 2: Configure environment variables (optional for alerts)

```bash
cp .env.example .env
# Edit .env and fill in TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, etc.
# Leave them blank if you don't want alerts yet — the pipeline still works.
```

### Step 3: Run the ETL pipeline

```bash
python -m etl.run_pipeline
```

You should see output like:
```
====================================================
  Processing: Dortmund
====================================================
[Extract] Fetching 30 days of weather for Dortmund...
[Extract] Done — 31 days downloaded.
[Transform] Flagged 0 anomalies out of 31 days (threshold: ±2.0σ).
[Load] Inserted 31 new rows. Total rows in DB: 31.
[Pipeline] No anomaly today for Dortmund — no alert sent.
```

### Step 4: Run the API

```bash
uvicorn app.main:app --reload
```

Then open in your browser:
- http://localhost:8000/docs — interactive API explorer
- http://localhost:8000/anomalies?city=Dortmund&days=30
- http://localhost:8000/weather?city=Dortmund&days=7

### Step 5: Run the tests

```bash
pytest tests/ -v
```

All tests should pass. Output will look like:
```
tests/test_transform.py::TestAddRollingStats::test_adds_rolling_mean_column PASSED
tests/test_transform.py::TestFlagAnomalies::test_extreme_spike_is_always_flagged PASSED
tests/test_api.py::TestHealthEndpoint::test_returns_200 PASSED
...
```

---

## Setup — Production Deployment

### Step 1: Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/weather-anomaly-tracker.git
git push -u origin main
```

### Step 2: Deploy the API to Render

1. Go to [render.com](https://render.com) → sign up (free)
2. Click **New → Web Service** → connect your GitHub repo
3. Render auto-detects `render.yaml` — just click **Create Web Service**
4. Add environment variable in the Render dashboard:
   ```
   DB_PATH = /opt/render/project/src/data/weather.db
   ```
5. Wait ~2 minutes for the first deploy to finish
6. Copy the deploy hook URL: **Settings → Deploy Hook**

### Step 3: Add GitHub Secrets

Go to your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret name         | Value                         | Required? |
|---------------------|-------------------------------|-----------|
| RENDER_DEPLOY_HOOK  | URL from Render dashboard     | Yes (for auto-deploy) |
| TELEGRAM_TOKEN      | From @BotFather on Telegram   | No        |
| TELEGRAM_CHAT_ID    | From @userinfobot on Telegram | No        |
| EMAIL_FROM          | your Gmail address            | No        |
| EMAIL_PASSWORD      | Gmail App Password (16 chars) | No        |
| EMAIL_TO            | alert destination email       | No        |

### Step 4: Test the CI/CD pipeline

Make a small change and push:
```bash
echo "# test" >> README.md
git add README.md
git commit -m "Test CI/CD"
git push
```

Go to GitHub → **Actions** tab. You should see the **CI — Test and Deploy** workflow running.
After it passes, Render will automatically redeploy your API.

### Step 5: Test the ETL workflow

Go to GitHub → **Actions → Daily ETL Pipeline → Run workflow**.
This manually triggers the pipeline so you don't have to wait until 08:00.

### Database persistence note

GitHub Actions VMs are temporary — `data/weather.db` is lost after each ETL run.
For persistent data, upgrade to **Supabase** (free):

1. Sign up at [supabase.com](https://supabase.com)
2. Create a project → copy the **Connection string** (PostgreSQL URI)
3. Add `psycopg2-binary` to `requirements.txt`
4. Update `app/db.py` and `etl/load.py` to connect via the URI
5. Add `SUPABASE_URL` as a GitHub Secret

---

## Adding a New City

Open `etl/extract.py` and add to the `CITIES` dict:

```python
CITIES = {
    "Dortmund": {"latitude": 51.514, "longitude": 7.468},
    "Stuttgart": {"latitude": 48.775, "longitude": 9.182},   # ← add here
}
```

Look up coordinates at [open-meteo.com](https://open-meteo.com).

Then add the city to the `CITIES` list in `etl/run_pipeline.py`.

---

## Architecture Summary

| Component         | Technology         | Purpose                                      |
|-------------------|--------------------|----------------------------------------------|
| Data source       | Open-Meteo API     | Free weather data, no API key needed         |
| ETL orchestration | Python + pandas    | Extract → Transform → Load                   |
| Scheduling        | GitHub Actions     | Cron job: runs pipeline daily at 08:00       |
| CI/CD             | GitHub Actions     | Tests on push, auto-deploy to Render on pass |
| Database          | SQLite             | Stores enriched weather rows                 |
| Web API           | FastAPI + uvicorn  | Serves anomaly data as JSON                  |
| Deployment        | Render.com         | Hosts the FastAPI app (free tier)            |
| Alerts            | Telegram / Gmail   | Notifies when an anomaly is detected         |

---

## Tech Stack

- **Python 3.11** — main language
- **pandas** — data manipulation and rolling statistics
- **requests** — HTTP calls to Open-Meteo API and Telegram
- **FastAPI** — building the REST API
- **uvicorn** — ASGI server that runs FastAPI
- **SQLite** — lightweight database (no server needed)
- **pytest** — testing framework
- **httpx** — HTTP client used by FastAPI's TestClient
- **GitHub Actions** — CI/CD and cron scheduling
- **Render.com** — cloud hosting (free tier)

---

## Skills Demonstrated

- **ETL pipeline** design (Extract → Transform → Load)
- **Statistical anomaly detection** (rolling Z-score)
- **REST API** development with FastAPI
- **CI/CD pipeline** with automated testing and deployment
- **Unit and integration testing** with pytest
- **Idempotent data loading** (safe to re-run)
- **Scheduled jobs** with GitHub Actions cron
- **Secret management** with GitHub Secrets
- **Cloud deployment** on Render

---

*Built as a portfolio project. Open-Meteo data is used under the CC BY 4.0 license.*
