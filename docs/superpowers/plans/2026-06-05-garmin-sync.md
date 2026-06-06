# Garmin Data Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync all health/sensor data from a Garmin Forerunner 965 (via Garmin Connect) into PostgreSQL, running as a daily k8s CronJob, with newest-first backfill to 2023-01-01.

**Architecture:** Flat modules (ticket-tracker style): `garmin_client.py` (auth + throttled API calls) → `normalizers.py` (pure JSON→row functions) → `db_client.py` (psycopg2 upserts) → `sync.py` (orchestrator) → `main.py` (entrypoint). Typed tables + raw JSONB on daily-level tables.

**Tech Stack:** Python 3.11, `garminconnect`, `psycopg2-binary`, `python-dotenv`, pytest + pytest-mock. PostgreSQL.

**Spec:** `docs/superpowers/specs/2026-06-05-garmin-sync-design.md`

**Refinement vs spec:** intraday tables (`hr_intraday`, etc.) do NOT carry a `raw JSONB` column — each row is a single primitive point; storing the full day payload per point would duplicate it ~700×. Raw payloads are kept on the daily-level tables (`daily_summary`, `sleep`, `hrv`, `training_status`, `activities`).

**Fixtures note:** fixture JSONs below are synthetic, built from the documented `garminconnect` payload shapes. Task 14 captures real payloads from the user's account and validates the normalizers against them — adjust fixtures/normalizers there if real shapes differ (especially `spo2.json`, whose key `spO2HourlyAverages` is the least certain).

**Conventions:**
- All work on branch `feat/garmin-sync` (hook blocks commits to `main`).
- Run tests from repo root: `python -m pytest tests/ -v`.
- Commit messages: Conventional Commits (`feat:`, `test:`, `chore:`).
- All timestamps stored UTC (`timestamptz`). Garmin epoch values are GMT milliseconds.

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `.gitignore`, `src/__init__.py`, `tests/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: Create requirements.txt**

```
garminconnect>=0.2.19
psycopg2-binary>=2.9
python-dotenv>=1.0
pytest>=8.0
pytest-mock>=3.12
```

- [ ] **Step 2: Create pytest.ini**

```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 3: Create .gitignore**

```
__pycache__/
*.pyc
.env
.venv/
venv/
.garminconnect/
.pytest_cache/
```

- [ ] **Step 4: Create package markers and conftest**

`src/__init__.py` and `tests/__init__.py`: empty files.

`tests/conftest.py`:

```python
import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES_DIR / name).read_text())
```

- [ ] **Step 5: Create venv, install, verify pytest runs**

Run:
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -v
```
Expected: `no tests ran` (exit code 5 is fine at this point).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pytest.ini .gitignore src/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: project scaffolding"
```

---

### Task 2: Fixture files

**Files:**
- Create: `fixtures/daily_summary.json`, `fixtures/sleep.json`, `fixtures/heart_rate.json`, `fixtures/stress.json`, `fixtures/body_battery.json`, `fixtures/respiration.json`, `fixtures/spo2.json`, `fixtures/steps.json`, `fixtures/hrv.json`, `fixtures/training_status.json`, `fixtures/activities.json`, `fixtures/activity_splits.json`

All timestamps derive from epoch `1700000000` = 2023-11-14T22:13:20Z; `calendar_date` for tests is `2023-11-14`.

- [ ] **Step 1: Create fixture files**

`fixtures/daily_summary.json`:
```json
{
  "calendarDate": "2023-11-14",
  "totalSteps": 9543,
  "totalKilocalories": 2450,
  "activeKilocalories": 612,
  "floorsAscended": 12.0,
  "moderateIntensityMinutes": 35,
  "vigorousIntensityMinutes": 20,
  "restingHeartRate": 47,
  "minHeartRate": 44,
  "maxHeartRate": 162
}
```

`fixtures/sleep.json`:
```json
{
  "dailySleepDTO": {
    "calendarDate": "2023-11-14",
    "sleepTimeSeconds": 27000,
    "deepSleepSeconds": 5400,
    "lightSleepSeconds": 14400,
    "remSleepSeconds": 5400,
    "awakeSleepSeconds": 1800,
    "averageSpO2Value": 95.0,
    "averageRespirationValue": 14.5,
    "sleepStartTimestampGMT": 1699998000000,
    "sleepEndTimestampGMT": 1700025000000,
    "sleepScores": {"overall": {"value": 82}}
  }
}
```

`fixtures/heart_rate.json`:
```json
{
  "calendarDate": "2023-11-14",
  "restingHeartRate": 47,
  "heartRateValues": [
    [1700000000000, 62],
    [1700000120000, 64],
    [1700000240000, null]
  ]
}
```

`fixtures/stress.json`:
```json
{
  "calendarDate": "2023-11-14",
  "stressValuesArray": [
    [1700000000000, 25],
    [1700000180000, -1],
    [1700000360000, 31]
  ]
}
```

`fixtures/body_battery.json`:
```json
[
  {
    "date": "2023-11-14",
    "charged": 55,
    "drained": 42,
    "bodyBatteryValuesArray": [
      [1700000000000, "MEASURED", 73, 1.0],
      [1700000180000, "MEASURED", 72, 1.0]
    ]
  }
]
```

`fixtures/respiration.json`:
```json
{
  "calendarDate": "2023-11-14",
  "respirationValuesArray": [
    [1700000000000, 14.0],
    [1700000120000, -1.0],
    [1700000240000, 15.0]
  ]
}
```

`fixtures/spo2.json`:
```json
{
  "calendarDate": "2023-11-14",
  "averageSpO2": 95.0,
  "lowestSpO2": 90,
  "spO2HourlyAverages": [
    [1700000000000, 95],
    [1700003600000, 94]
  ]
}
```

`fixtures/steps.json`:
```json
[
  {"startGMT": "2023-11-14T00:00:00.0", "endGMT": "2023-11-14T00:15:00.0", "steps": 0, "primaryActivityLevel": "sleeping"},
  {"startGMT": "2023-11-14T08:00:00.0", "endGMT": "2023-11-14T08:15:00.0", "steps": 420, "primaryActivityLevel": "active"}
]
```

`fixtures/hrv.json`:
```json
{
  "hrvSummary": {
    "calendarDate": "2023-11-14",
    "lastNightAvg": 58,
    "weeklyAvg": 55,
    "status": "BALANCED"
  },
  "hrvReadings": []
}
```

`fixtures/training_status.json`:
```json
{
  "mostRecentVO2Max": {"generic": {"vo2MaxValue": 54.0}},
  "mostRecentTrainingStatus": {
    "latestTrainingStatusData": {
      "3472179884": {
        "trainingStatus": 4,
        "trainingStatusFeedbackPhrase": "PRODUCTIVE_1",
        "acuteTrainingLoadDTO": {"dailyTrainingLoadAcute": 612.0}
      }
    }
  }
}
```

`fixtures/activities.json`:
```json
[
  {
    "activityId": 12345678901,
    "activityName": "Valencia Running",
    "activityType": {"typeKey": "running"},
    "startTimeGMT": "2023-11-14 07:30:00",
    "distance": 10000.0,
    "duration": 3000.0,
    "averageHR": 150.0,
    "maxHR": 175.0,
    "averageSpeed": 3.333,
    "calories": 600.0,
    "vO2MaxValue": 54.0,
    "aerobicTrainingEffect": 3.5,
    "anaerobicTrainingEffect": 1.2
  }
]
```

`fixtures/activity_splits.json`:
```json
{
  "activityId": 12345678901,
  "lapDTOs": [
    {"lapIndex": 1, "distance": 1000.0, "duration": 295.0, "averageHR": 145.0, "averageSpeed": 3.39, "elevationGain": 5.0},
    {"lapIndex": 2, "distance": 1000.0, "duration": 301.0, "averageHR": 152.0, "averageSpeed": 3.32, "elevationGain": 8.0}
  ]
}
```

- [ ] **Step 2: Commit**

```bash
git add fixtures/
git commit -m "test: add synthetic Garmin API fixtures"
```

---

### Task 3: Schema + DB connection

**Files:**
- Create: `sql/schema.sql`, `src/db_client.py`
- Test: `tests/test_db_client.py`

- [ ] **Step 1: Write sql/schema.sql**

```sql
CREATE TABLE IF NOT EXISTS daily_summary (
    calendar_date DATE PRIMARY KEY,
    steps INTEGER,
    calories_total INTEGER,
    calories_active INTEGER,
    floors REAL,
    intensity_minutes_moderate INTEGER,
    intensity_minutes_vigorous INTEGER,
    resting_hr INTEGER,
    min_hr INTEGER,
    max_hr INTEGER,
    raw JSONB
);

CREATE TABLE IF NOT EXISTS sleep (
    calendar_date DATE PRIMARY KEY,
    score INTEGER,
    duration_sec INTEGER,
    deep_sec INTEGER,
    light_sec INTEGER,
    rem_sec INTEGER,
    awake_sec INTEGER,
    avg_spo2 REAL,
    avg_respiration REAL,
    sleep_start TIMESTAMPTZ,
    sleep_end TIMESTAMPTZ,
    raw JSONB
);

CREATE TABLE IF NOT EXISTS hrv (
    calendar_date DATE PRIMARY KEY,
    last_night_avg_ms REAL,
    weekly_avg_ms REAL,
    status TEXT,
    raw JSONB
);

CREATE TABLE IF NOT EXISTS training_status (
    calendar_date DATE PRIMARY KEY,
    vo2max REAL,
    training_load_7d REAL,
    status TEXT,
    raw JSONB
);

CREATE TABLE IF NOT EXISTS hr_intraday (
    calendar_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    bpm INTEGER,
    PRIMARY KEY (calendar_date, ts)
);

CREATE TABLE IF NOT EXISTS stress_intraday (
    calendar_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    stress_level INTEGER,
    PRIMARY KEY (calendar_date, ts)
);

CREATE TABLE IF NOT EXISTS body_battery_intraday (
    calendar_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    level INTEGER,
    PRIMARY KEY (calendar_date, ts)
);

CREATE TABLE IF NOT EXISTS respiration_intraday (
    calendar_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    breaths_per_min REAL,
    PRIMARY KEY (calendar_date, ts)
);

CREATE TABLE IF NOT EXISTS spo2_intraday (
    calendar_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    spo2_pct REAL,
    PRIMARY KEY (calendar_date, ts)
);

CREATE TABLE IF NOT EXISTS steps_intraday (
    calendar_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    steps INTEGER,
    PRIMARY KEY (calendar_date, ts)
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id BIGINT PRIMARY KEY,
    type TEXT,
    name TEXT,
    start_time TIMESTAMPTZ,
    distance_m REAL,
    duration_sec REAL,
    avg_hr REAL,
    max_hr REAL,
    avg_pace_s_per_km REAL,
    calories REAL,
    vo2max REAL,
    aerobic_training_effect REAL,
    anaerobic_training_effect REAL,
    raw JSONB
);

CREATE TABLE IF NOT EXISTS activity_splits (
    activity_id BIGINT NOT NULL,
    split_index INTEGER NOT NULL,
    distance_m REAL,
    duration_sec REAL,
    avg_hr REAL,
    avg_pace_s_per_km REAL,
    elevation_gain_m REAL,
    PRIMARY KEY (activity_id, split_index)
);

CREATE TABLE IF NOT EXISTS sync_log (
    calendar_date DATE PRIMARY KEY,
    synced_at TIMESTAMPTZ DEFAULT now()
);
```

- [ ] **Step 2: Write failing tests**

`tests/test_db_client.py`:

```python
import pytest


@pytest.fixture
def db(mocker):
    mocker.patch("src.db_client.psycopg2.connect")
    from src.db_client import GarminDB
    return GarminDB(host="h", port=5432, database="d", username="u", password="p")


@pytest.fixture
def cur(db):
    return db._conn.cursor.return_value.__enter__.return_value


def test_connects_on_init(mocker):
    connect = mocker.patch("src.db_client.psycopg2.connect")
    from src.db_client import GarminDB
    GarminDB(host="h", port=5432, database="d", username="u", password="p")
    connect.assert_called_once_with(host="h", port=5432, dbname="d", user="u", password="p")


def test_connection_error_raises_runtime_error(mocker):
    import psycopg2
    mocker.patch("src.db_client.psycopg2.connect", side_effect=psycopg2.OperationalError("boom"))
    from src.db_client import GarminDB
    with pytest.raises(RuntimeError, match="Cannot connect"):
        GarminDB(host="h", port=5432, database="d", username="u", password="p")


def test_create_tables_executes_schema(db, cur, tmp_path):
    schema = tmp_path / "schema.sql"
    schema.write_text("CREATE TABLE IF NOT EXISTS x (id INT);")
    db.create_tables(str(schema))
    cur.execute.assert_called_once_with("CREATE TABLE IF NOT EXISTS x (id INT);")
    db._conn.commit.assert_called_once()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_db_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.db_client'`.

- [ ] **Step 4: Write minimal implementation**

`src/db_client.py`:

```python
import psycopg2
import psycopg2.extras


class GarminDB:
    def __init__(self, host: str, port: int, database: str, username: str, password: str):
        try:
            self._conn = psycopg2.connect(
                host=host, port=port, dbname=database,
                user=username, password=password,
            )
        except psycopg2.Error as exc:
            raise RuntimeError(f"Cannot connect to PostgreSQL at {host}:{port} — {exc}") from exc

    def create_tables(self, schema_path: str) -> None:
        with open(schema_path) as f:
            sql = f.read()
        with self._conn.cursor() as cur:
            cur.execute(sql)
        self._conn.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_db_client.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add sql/schema.sql src/db_client.py tests/test_db_client.py
git commit -m "feat: DB schema and connection"
```

---

### Task 4: Normalizers — daily_summary + sleep

**Files:**
- Create: `src/normalizers.py`
- Test: `tests/test_normalizers.py`

- [ ] **Step 1: Write failing tests**

`tests/test_normalizers.py`:

```python
from datetime import date, datetime, timezone

from tests.conftest import load_fixture

DAY = date(2023, 11, 14)


# --- daily_summary ---

def test_normalize_daily_summary():
    from src.normalizers import normalize_daily_summary
    payload = load_fixture("daily_summary.json")
    row = normalize_daily_summary(payload, DAY)
    assert row == {
        "calendar_date": DAY,
        "steps": 9543,
        "calories_total": 2450,
        "calories_active": 612,
        "floors": 12.0,
        "intensity_minutes_moderate": 35,
        "intensity_minutes_vigorous": 20,
        "resting_hr": 47,
        "min_hr": 44,
        "max_hr": 162,
        "raw": payload,
    }


def test_normalize_daily_summary_empty_returns_none():
    from src.normalizers import normalize_daily_summary
    assert normalize_daily_summary(None, DAY) is None
    assert normalize_daily_summary({}, DAY) is None


# --- sleep ---

def test_normalize_sleep():
    from src.normalizers import normalize_sleep
    payload = load_fixture("sleep.json")
    row = normalize_sleep(payload, DAY)
    assert row["calendar_date"] == DAY
    assert row["score"] == 82
    assert row["duration_sec"] == 27000
    assert row["deep_sec"] == 5400
    assert row["light_sec"] == 14400
    assert row["rem_sec"] == 5400
    assert row["awake_sec"] == 1800
    assert row["avg_spo2"] == 95.0
    assert row["avg_respiration"] == 14.5
    assert row["sleep_start"] == datetime.fromtimestamp(1699998000, tz=timezone.utc)
    assert row["sleep_end"] == datetime.fromtimestamp(1700025000, tz=timezone.utc)
    assert row["raw"] == payload


def test_normalize_sleep_no_data_returns_none():
    from src.normalizers import normalize_sleep
    assert normalize_sleep(None, DAY) is None
    assert normalize_sleep({}, DAY) is None
    assert normalize_sleep({"dailySleepDTO": {"sleepTimeSeconds": 0}}, DAY) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_normalizers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.normalizers'`.

- [ ] **Step 3: Write minimal implementation**

`src/normalizers.py`:

```python
from datetime import date, datetime, timezone


def _ts(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def normalize_daily_summary(payload: dict | None, calendar_date: date) -> dict | None:
    if not payload:
        return None
    return {
        "calendar_date": calendar_date,
        "steps": payload.get("totalSteps"),
        "calories_total": payload.get("totalKilocalories"),
        "calories_active": payload.get("activeKilocalories"),
        "floors": payload.get("floorsAscended"),
        "intensity_minutes_moderate": payload.get("moderateIntensityMinutes"),
        "intensity_minutes_vigorous": payload.get("vigorousIntensityMinutes"),
        "resting_hr": payload.get("restingHeartRate"),
        "min_hr": payload.get("minHeartRate"),
        "max_hr": payload.get("maxHeartRate"),
        "raw": payload,
    }


def normalize_sleep(payload: dict | None, calendar_date: date) -> dict | None:
    dto = (payload or {}).get("dailySleepDTO") or {}
    if not dto.get("sleepTimeSeconds"):
        return None
    scores = (dto.get("sleepScores") or {}).get("overall") or {}
    return {
        "calendar_date": calendar_date,
        "score": scores.get("value"),
        "duration_sec": dto.get("sleepTimeSeconds"),
        "deep_sec": dto.get("deepSleepSeconds"),
        "light_sec": dto.get("lightSleepSeconds"),
        "rem_sec": dto.get("remSleepSeconds"),
        "awake_sec": dto.get("awakeSleepSeconds"),
        "avg_spo2": dto.get("averageSpO2Value"),
        "avg_respiration": dto.get("averageRespirationValue"),
        "sleep_start": _ts(dto["sleepStartTimestampGMT"]) if dto.get("sleepStartTimestampGMT") else None,
        "sleep_end": _ts(dto["sleepEndTimestampGMT"]) if dto.get("sleepEndTimestampGMT") else None,
        "raw": payload,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_normalizers.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/normalizers.py tests/test_normalizers.py
git commit -m "feat: daily summary and sleep normalizers"
```

---

### Task 5: Normalizers — HR, stress, body battery intraday

**Files:**
- Modify: `src/normalizers.py`
- Test: `tests/test_normalizers.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_normalizers.py`)

```python
# --- hr_intraday ---

def test_normalize_hr_intraday():
    from src.normalizers import normalize_hr_intraday
    rows = normalize_hr_intraday(load_fixture("heart_rate.json"), DAY)
    assert rows == [
        {"calendar_date": DAY, "ts": datetime.fromtimestamp(1700000000, tz=timezone.utc), "bpm": 62},
        {"calendar_date": DAY, "ts": datetime.fromtimestamp(1700000120, tz=timezone.utc), "bpm": 64},
    ]  # null bpm point dropped


def test_normalize_hr_intraday_empty():
    from src.normalizers import normalize_hr_intraday
    assert normalize_hr_intraday(None, DAY) == []
    assert normalize_hr_intraday({}, DAY) == []


# --- stress_intraday ---

def test_normalize_stress_intraday_drops_negative_levels():
    from src.normalizers import normalize_stress_intraday
    rows = normalize_stress_intraday(load_fixture("stress.json"), DAY)
    assert rows == [
        {"calendar_date": DAY, "ts": datetime.fromtimestamp(1700000000, tz=timezone.utc), "stress_level": 25},
        {"calendar_date": DAY, "ts": datetime.fromtimestamp(1700000360, tz=timezone.utc), "stress_level": 31},
    ]  # -1 (off-wrist) dropped


# --- body_battery_intraday ---

def test_normalize_body_battery_intraday():
    from src.normalizers import normalize_body_battery_intraday
    rows = normalize_body_battery_intraday(load_fixture("body_battery.json"), DAY)
    assert rows == [
        {"calendar_date": DAY, "ts": datetime.fromtimestamp(1700000000, tz=timezone.utc), "level": 73},
        {"calendar_date": DAY, "ts": datetime.fromtimestamp(1700000180, tz=timezone.utc), "level": 72},
    ]


def test_normalize_body_battery_intraday_empty():
    from src.normalizers import normalize_body_battery_intraday
    assert normalize_body_battery_intraday(None, DAY) == []
    assert normalize_body_battery_intraday([], DAY) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_normalizers.py -v`
Expected: new tests FAIL with ImportError; Task 4 tests still PASS.

- [ ] **Step 3: Implement** (append to `src/normalizers.py`)

```python
def normalize_hr_intraday(payload: dict | None, calendar_date: date) -> list[dict]:
    values = (payload or {}).get("heartRateValues") or []
    return [
        {"calendar_date": calendar_date, "ts": _ts(ts), "bpm": bpm}
        for ts, bpm in values
        if bpm is not None
    ]


def normalize_stress_intraday(payload: dict | None, calendar_date: date) -> list[dict]:
    values = (payload or {}).get("stressValuesArray") or []
    return [
        {"calendar_date": calendar_date, "ts": _ts(ts), "stress_level": level}
        for ts, level in values
        if level is not None and level >= 0
    ]


def normalize_body_battery_intraday(payload: list | None, calendar_date: date) -> list[dict]:
    rows = []
    for day in payload or []:
        for point in day.get("bodyBatteryValuesArray") or []:
            ts, level = point[0], point[2]
            if level is not None:
                rows.append({"calendar_date": calendar_date, "ts": _ts(ts), "level": level})
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_normalizers.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/normalizers.py tests/test_normalizers.py
git commit -m "feat: HR, stress, body battery intraday normalizers"
```

---

### Task 6: Normalizers — respiration, SpO2, steps intraday

**Files:**
- Modify: `src/normalizers.py`
- Test: `tests/test_normalizers.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_normalizers.py`)

```python
# --- respiration_intraday ---

def test_normalize_respiration_intraday_drops_negatives():
    from src.normalizers import normalize_respiration_intraday
    rows = normalize_respiration_intraday(load_fixture("respiration.json"), DAY)
    assert rows == [
        {"calendar_date": DAY, "ts": datetime.fromtimestamp(1700000000, tz=timezone.utc), "breaths_per_min": 14.0},
        {"calendar_date": DAY, "ts": datetime.fromtimestamp(1700000240, tz=timezone.utc), "breaths_per_min": 15.0},
    ]


# --- spo2_intraday ---

def test_normalize_spo2_intraday():
    from src.normalizers import normalize_spo2_intraday
    rows = normalize_spo2_intraday(load_fixture("spo2.json"), DAY)
    assert rows == [
        {"calendar_date": DAY, "ts": datetime.fromtimestamp(1700000000, tz=timezone.utc), "spo2_pct": 95},
        {"calendar_date": DAY, "ts": datetime.fromtimestamp(1700003600, tz=timezone.utc), "spo2_pct": 94},
    ]


def test_normalize_spo2_intraday_empty():
    from src.normalizers import normalize_spo2_intraday
    assert normalize_spo2_intraday(None, DAY) == []
    assert normalize_spo2_intraday({}, DAY) == []


# --- steps_intraday ---

def test_normalize_steps_intraday():
    from src.normalizers import normalize_steps_intraday
    rows = normalize_steps_intraday(load_fixture("steps.json"), DAY)
    assert rows == [
        {"calendar_date": DAY, "ts": datetime(2023, 11, 14, 0, 0, tzinfo=timezone.utc), "steps": 0},
        {"calendar_date": DAY, "ts": datetime(2023, 11, 14, 8, 0, tzinfo=timezone.utc), "steps": 420},
    ]


def test_normalize_steps_intraday_empty():
    from src.normalizers import normalize_steps_intraday
    assert normalize_steps_intraday(None, DAY) == []
    assert normalize_steps_intraday([], DAY) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_normalizers.py -v`
Expected: new tests FAIL with ImportError.

- [ ] **Step 3: Implement** (append to `src/normalizers.py`)

```python
def normalize_respiration_intraday(payload: dict | None, calendar_date: date) -> list[dict]:
    values = (payload or {}).get("respirationValuesArray") or []
    return [
        {"calendar_date": calendar_date, "ts": _ts(ts), "breaths_per_min": breaths}
        for ts, breaths in values
        if breaths is not None and breaths >= 0
    ]


def normalize_spo2_intraday(payload: dict | None, calendar_date: date) -> list[dict]:
    values = (payload or {}).get("spO2HourlyAverages") or []
    return [
        {"calendar_date": calendar_date, "ts": _ts(ts), "spo2_pct": pct}
        for ts, pct in values
        if pct is not None
    ]


def normalize_steps_intraday(payload: list | None, calendar_date: date) -> list[dict]:
    rows = []
    for bucket in payload or []:
        start = bucket.get("startGMT")
        steps = bucket.get("steps")
        if start is None or steps is None:
            continue
        ts = datetime.strptime(start, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
        rows.append({"calendar_date": calendar_date, "ts": ts, "steps": steps})
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_normalizers.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/normalizers.py tests/test_normalizers.py
git commit -m "feat: respiration, SpO2, steps intraday normalizers"
```

---

### Task 7: Normalizers — HRV + training status

**Files:**
- Modify: `src/normalizers.py`
- Test: `tests/test_normalizers.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_normalizers.py`)

```python
# --- hrv ---

def test_normalize_hrv():
    from src.normalizers import normalize_hrv
    payload = load_fixture("hrv.json")
    row = normalize_hrv(payload, DAY)
    assert row == {
        "calendar_date": DAY,
        "last_night_avg_ms": 58,
        "weekly_avg_ms": 55,
        "status": "BALANCED",
        "raw": payload,
    }


def test_normalize_hrv_no_data_returns_none():
    from src.normalizers import normalize_hrv
    assert normalize_hrv(None, DAY) is None
    assert normalize_hrv({}, DAY) is None


# --- training_status ---

def test_normalize_training_status():
    from src.normalizers import normalize_training_status
    payload = load_fixture("training_status.json")
    row = normalize_training_status(payload, DAY)
    assert row == {
        "calendar_date": DAY,
        "vo2max": 54.0,
        "training_load_7d": 612.0,
        "status": "PRODUCTIVE_1",
        "raw": payload,
    }


def test_normalize_training_status_no_data_returns_none():
    from src.normalizers import normalize_training_status
    assert normalize_training_status(None, DAY) is None
    assert normalize_training_status({}, DAY) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_normalizers.py -v`
Expected: new tests FAIL with ImportError.

- [ ] **Step 3: Implement** (append to `src/normalizers.py`)

```python
def normalize_hrv(payload: dict | None, calendar_date: date) -> dict | None:
    summary = (payload or {}).get("hrvSummary") or {}
    if not summary:
        return None
    return {
        "calendar_date": calendar_date,
        "last_night_avg_ms": summary.get("lastNightAvg"),
        "weekly_avg_ms": summary.get("weeklyAvg"),
        "status": summary.get("status"),
        "raw": payload,
    }


def normalize_training_status(payload: dict | None, calendar_date: date) -> dict | None:
    if not payload:
        return None
    vo2 = (payload.get("mostRecentVO2Max") or {}).get("generic") or {}
    status_block = (payload.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData") or {}
    device_data = next(iter(status_block.values()), {})
    load = device_data.get("acuteTrainingLoadDTO") or {}
    if not vo2 and not device_data:
        return None
    return {
        "calendar_date": calendar_date,
        "vo2max": vo2.get("vo2MaxValue"),
        "training_load_7d": load.get("dailyTrainingLoadAcute"),
        "status": device_data.get("trainingStatusFeedbackPhrase"),
        "raw": payload,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_normalizers.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/normalizers.py tests/test_normalizers.py
git commit -m "feat: HRV and training status normalizers"
```

---

### Task 8: Normalizers — activities + splits

**Files:**
- Modify: `src/normalizers.py`
- Test: `tests/test_normalizers.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_normalizers.py`)

```python
# --- activities ---

def test_normalize_activity():
    from src.normalizers import normalize_activity
    payload = load_fixture("activities.json")[0]
    row = normalize_activity(payload)
    assert row["activity_id"] == 12345678901
    assert row["type"] == "running"
    assert row["name"] == "Valencia Running"
    assert row["start_time"] == datetime(2023, 11, 14, 7, 30, tzinfo=timezone.utc)
    assert row["distance_m"] == 10000.0
    assert row["duration_sec"] == 3000.0
    assert row["avg_hr"] == 150.0
    assert row["max_hr"] == 175.0
    assert row["avg_pace_s_per_km"] == 1000 / 3.333
    assert row["calories"] == 600.0
    assert row["vo2max"] == 54.0
    assert row["aerobic_training_effect"] == 3.5
    assert row["anaerobic_training_effect"] == 1.2
    assert row["raw"] == payload


def test_normalize_activity_zero_speed_gives_null_pace():
    from src.normalizers import normalize_activity
    payload = load_fixture("activities.json")[0] | {"averageSpeed": 0}
    assert normalize_activity(payload)["avg_pace_s_per_km"] is None


# --- activity_splits ---

def test_normalize_activity_splits():
    from src.normalizers import normalize_activity_splits
    payload = load_fixture("activity_splits.json")
    rows = normalize_activity_splits(payload, 12345678901)
    assert len(rows) == 2
    assert rows[0] == {
        "activity_id": 12345678901,
        "split_index": 0,
        "distance_m": 1000.0,
        "duration_sec": 295.0,
        "avg_hr": 145.0,
        "avg_pace_s_per_km": 1000 / 3.39,
        "elevation_gain_m": 5.0,
    }
    assert rows[1]["split_index"] == 1


def test_normalize_activity_splits_empty():
    from src.normalizers import normalize_activity_splits
    assert normalize_activity_splits(None, 1) == []
    assert normalize_activity_splits({}, 1) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_normalizers.py -v`
Expected: new tests FAIL with ImportError.

- [ ] **Step 3: Implement** (append to `src/normalizers.py`)

```python
def normalize_activity(payload: dict) -> dict:
    speed = payload.get("averageSpeed")
    return {
        "activity_id": payload["activityId"],
        "type": (payload.get("activityType") or {}).get("typeKey"),
        "name": payload.get("activityName"),
        "start_time": datetime.strptime(payload["startTimeGMT"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc),
        "distance_m": payload.get("distance"),
        "duration_sec": payload.get("duration"),
        "avg_hr": payload.get("averageHR"),
        "max_hr": payload.get("maxHR"),
        "avg_pace_s_per_km": 1000 / speed if speed else None,
        "calories": payload.get("calories"),
        "vo2max": payload.get("vO2MaxValue"),
        "aerobic_training_effect": payload.get("aerobicTrainingEffect"),
        "anaerobic_training_effect": payload.get("anaerobicTrainingEffect"),
        "raw": payload,
    }


def normalize_activity_splits(payload: dict | None, activity_id: int) -> list[dict]:
    rows = []
    for i, lap in enumerate((payload or {}).get("lapDTOs") or []):
        speed = lap.get("averageSpeed")
        rows.append({
            "activity_id": activity_id,
            "split_index": i,
            "distance_m": lap.get("distance"),
            "duration_sec": lap.get("duration"),
            "avg_hr": lap.get("averageHR"),
            "avg_pace_s_per_km": 1000 / speed if speed else None,
            "elevation_gain_m": lap.get("elevationGain"),
        })
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_normalizers.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/normalizers.py tests/test_normalizers.py
git commit -m "feat: activity and splits normalizers"
```

---

### Task 9: DB upserts

**Files:**
- Modify: `src/db_client.py`
- Test: `tests/test_db_client.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_db_client.py`)

```python
from datetime import date, datetime, timezone

DAY = date(2023, 11, 14)
TS = datetime(2023, 11, 14, 8, 0, tzinfo=timezone.utc)


def test_upsert_daily_summary_sql(db, cur):
    row = {"calendar_date": DAY, "steps": 100, "raw": {"a": 1}}
    db.upsert_daily_summary(row)
    sql, params = cur.execute.call_args[0]
    assert "INSERT INTO daily_summary" in sql
    assert "ON CONFLICT (calendar_date) DO UPDATE" in sql
    assert "steps = EXCLUDED.steps" in sql
    assert "raw = EXCLUDED.raw" in sql
    assert "calendar_date = EXCLUDED" not in sql  # PK not updated
    assert params[0] == DAY
    assert params[1] == 100
    import psycopg2.extras
    assert isinstance(params[2], psycopg2.extras.Json)  # dicts wrapped for JSONB
    db._conn.commit.assert_called_once()


def test_upsert_sleep_hrv_training_status_route_to_tables(db, cur):
    db.upsert_sleep({"calendar_date": DAY, "score": 80})
    db.upsert_hrv({"calendar_date": DAY, "status": "BALANCED"})
    db.upsert_training_status({"calendar_date": DAY, "vo2max": 54.0})
    sqls = [c[0][0] for c in cur.execute.call_args_list]
    assert "INSERT INTO sleep" in sqls[0]
    assert "INSERT INTO hrv" in sqls[1]
    assert "INSERT INTO training_status" in sqls[2]


def test_upsert_intraday_uses_execute_values(db, cur, mocker):
    ev = mocker.patch("src.db_client.psycopg2.extras.execute_values")
    rows = [{"calendar_date": DAY, "ts": TS, "bpm": 62}]
    db.upsert_intraday("hr_intraday", ["bpm"], rows)
    sql = ev.call_args[0][1]
    values = ev.call_args[0][2]
    assert "INSERT INTO hr_intraday (calendar_date, ts, bpm)" in sql
    assert "ON CONFLICT (calendar_date, ts) DO UPDATE" in sql
    assert values == [(DAY, TS, 62)]
    db._conn.commit.assert_called_once()


def test_upsert_intraday_no_rows_is_noop(db, cur, mocker):
    ev = mocker.patch("src.db_client.psycopg2.extras.execute_values")
    db.upsert_intraday("hr_intraday", ["bpm"], [])
    ev.assert_not_called()


def test_upsert_activity_and_splits(db, cur, mocker):
    ev = mocker.patch("src.db_client.psycopg2.extras.execute_values")
    db.upsert_activity({"activity_id": 1, "type": "running", "raw": {}})
    sql = cur.execute.call_args[0][0]
    assert "INSERT INTO activities" in sql
    assert "ON CONFLICT (activity_id) DO UPDATE" in sql

    db.upsert_activity_splits([
        {"activity_id": 1, "split_index": 0, "distance_m": 1000.0},
    ])
    sql = ev.call_args[0][1]
    assert "INSERT INTO activity_splits" in sql
    assert "ON CONFLICT (activity_id, split_index) DO UPDATE" in sql
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_db_client.py -v`
Expected: new tests FAIL — `AttributeError: 'GarminDB' object has no attribute 'upsert_daily_summary'`.

- [ ] **Step 3: Implement** (append methods to `GarminDB` in `src/db_client.py`)

```python
    def _upsert(self, table: str, pk_cols: list[str], row: dict) -> None:
        cols = list(row.keys())
        update_cols = [c for c in cols if c not in pk_cols]
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) "
            f"VALUES ({', '.join(['%s'] * len(cols))}) "
            f"ON CONFLICT ({', '.join(pk_cols)}) DO UPDATE SET "
            + ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        )
        params = [
            psycopg2.extras.Json(v) if isinstance(v, (dict, list)) else v
            for v in row.values()
        ]
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
        self._conn.commit()

    def upsert_daily_summary(self, row: dict) -> None:
        self._upsert("daily_summary", ["calendar_date"], row)

    def upsert_sleep(self, row: dict) -> None:
        self._upsert("sleep", ["calendar_date"], row)

    def upsert_hrv(self, row: dict) -> None:
        self._upsert("hrv", ["calendar_date"], row)

    def upsert_training_status(self, row: dict) -> None:
        self._upsert("training_status", ["calendar_date"], row)

    def upsert_activity(self, row: dict) -> None:
        self._upsert("activities", ["activity_id"], row)

    def upsert_intraday(self, table: str, value_cols: list[str], rows: list[dict]) -> None:
        if not rows:
            return
        cols = ["calendar_date", "ts"] + value_cols
        update = ", ".join(f"{c} = EXCLUDED.{c}" for c in value_cols)
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s "
            f"ON CONFLICT (calendar_date, ts) DO UPDATE SET {update}"
        )
        with self._conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, [tuple(r[c] for c in cols) for r in rows])
        self._conn.commit()

    def upsert_activity_splits(self, rows: list[dict]) -> None:
        if not rows:
            return
        cols = ["activity_id", "split_index", "distance_m", "duration_sec",
                "avg_hr", "avg_pace_s_per_km", "elevation_gain_m"]
        update = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols[2:])
        sql = (
            f"INSERT INTO activity_splits ({', '.join(cols)}) VALUES %s "
            f"ON CONFLICT (activity_id, split_index) DO UPDATE SET {update}"
        )
        with self._conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur, sql, [tuple(r.get(c) for c in cols) for r in rows]
            )
        self._conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_db_client.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/db_client.py tests/test_db_client.py
git commit -m "feat: DB upserts for all tables"
```

---

### Task 10: DB sync state

**Files:**
- Modify: `src/db_client.py`
- Test: `tests/test_db_client.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_db_client.py`)

```python
def test_get_synced_dates(db, cur):
    cur.fetchall.return_value = [(date(2023, 11, 14),), (date(2023, 11, 13),)]
    result = db.get_synced_dates()
    assert result == {date(2023, 11, 14), date(2023, 11, 13)}
    assert "SELECT calendar_date FROM sync_log" in cur.execute.call_args[0][0]


def test_mark_synced(db, cur):
    db.mark_synced(DAY)
    sql, params = cur.execute.call_args[0]
    assert "INSERT INTO sync_log" in sql
    assert "ON CONFLICT (calendar_date) DO NOTHING" in sql
    assert params == (DAY,)
    db._conn.commit.assert_called_once()


def test_get_latest_activity_start(db, cur):
    cur.fetchone.return_value = (TS,)
    assert db.get_latest_activity_start() == TS
    assert "SELECT max(start_time) FROM activities" in cur.execute.call_args[0][0]


def test_get_latest_activity_start_empty_table(db, cur):
    cur.fetchone.return_value = (None,)
    assert db.get_latest_activity_start() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_db_client.py -v`
Expected: new tests FAIL — AttributeError.

- [ ] **Step 3: Implement** (append methods to `GarminDB`)

```python
    def get_synced_dates(self) -> set:
        with self._conn.cursor() as cur:
            cur.execute("SELECT calendar_date FROM sync_log")
            return {r[0] for r in cur.fetchall()}

    def mark_synced(self, calendar_date) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sync_log (calendar_date) VALUES (%s) "
                "ON CONFLICT (calendar_date) DO NOTHING",
                (calendar_date,),
            )
        self._conn.commit()

    def get_latest_activity_start(self):
        with self._conn.cursor() as cur:
            cur.execute("SELECT max(start_time) FROM activities")
            return cur.fetchone()[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_db_client.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/db_client.py tests/test_db_client.py
git commit -m "feat: sync state queries"
```

---

### Task 11: Garmin client — auth, throttle, endpoints

**Files:**
- Create: `src/garmin_client.py`
- Test: `tests/test_garmin_client.py`

- [ ] **Step 1: Write failing tests**

`tests/test_garmin_client.py`:

```python
from datetime import date

import pytest

DAY = date(2023, 11, 14)


@pytest.fixture
def garmin_cls(mocker):
    return mocker.patch("src.garmin_client.Garmin")


@pytest.fixture
def sleep_mock(mocker):
    return mocker.patch("src.garmin_client.time.sleep")


def make_client(throttle=0.0):
    from src.garmin_client import GarminClient
    return GarminClient(email="e@x.com", password="pw", tokenstore="/tokens", throttle_seconds=throttle)


def test_login_with_tokens_first(garmin_cls, sleep_mock):
    make_client()
    garmin_cls.assert_called_once_with()  # no credentials passed
    garmin_cls.return_value.login.assert_called_once_with("/tokens")


def test_login_falls_back_to_credentials(garmin_cls, sleep_mock):
    token_api = garmin_cls.return_value
    token_api.login.side_effect = [FileNotFoundError("no tokens"), None]
    make_client()
    # Second construction with credentials, login persists tokens to tokenstore
    assert garmin_cls.call_count == 2
    assert garmin_cls.call_args_list[1].kwargs == {"email": "e@x.com", "password": "pw"}


def test_calls_are_throttled(garmin_cls, sleep_mock):
    client = make_client(throttle=1.5)
    client.get_sleep(DAY)
    sleep_mock.assert_called_with(1.5)


def test_429_backs_off_60s_and_retries_once(garmin_cls, sleep_mock):
    from garminconnect import GarminConnectTooManyRequestsError
    api = garmin_cls.return_value
    api.get_sleep_data.side_effect = [GarminConnectTooManyRequestsError("429"), {"ok": 1}]
    client = make_client()
    assert client.get_sleep(DAY) == {"ok": 1}
    assert sleep_mock.call_args_list[-1].args == (60,)


def test_second_429_propagates(garmin_cls, sleep_mock):
    from garminconnect import GarminConnectTooManyRequestsError
    api = garmin_cls.return_value
    api.get_sleep_data.side_effect = GarminConnectTooManyRequestsError("429")
    client = make_client()
    with pytest.raises(GarminConnectTooManyRequestsError):
        client.get_sleep(DAY)


def test_endpoints_pass_isodate(garmin_cls, sleep_mock):
    api = garmin_cls.return_value
    client = make_client()
    client.get_daily_summary(DAY)
    api.get_stats.assert_called_once_with("2023-11-14")
    client.get_heart_rate(DAY)
    api.get_heart_rates.assert_called_once_with("2023-11-14")
    client.get_stress(DAY)
    api.get_stress_data.assert_called_once_with("2023-11-14")
    client.get_body_battery(DAY)
    api.get_body_battery.assert_called_once_with("2023-11-14")
    client.get_respiration(DAY)
    api.get_respiration_data.assert_called_once_with("2023-11-14")
    client.get_spo2(DAY)
    api.get_spo2_data.assert_called_once_with("2023-11-14")
    client.get_steps(DAY)
    api.get_steps_data.assert_called_once_with("2023-11-14")
    client.get_hrv(DAY)
    api.get_hrv_data.assert_called_once_with("2023-11-14")
    client.get_training_status(DAY)
    api.get_training_status.assert_called_once_with("2023-11-14")
    client.get_activities(0, 50)
    api.get_activities.assert_called_once_with(0, 50)
    client.get_activity_splits(123)
    api.get_activity_splits.assert_called_once_with(123)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_garmin_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.garmin_client'`.

- [ ] **Step 3: Write implementation**

`src/garmin_client.py`:

```python
import logging
import time
from datetime import date

from garminconnect import Garmin, GarminConnectTooManyRequestsError

log = logging.getLogger(__name__)


class GarminClient:
    def __init__(self, email: str, password: str, tokenstore: str, throttle_seconds: float = 1.0):
        self._email = email
        self._password = password
        self._tokenstore = tokenstore
        self._throttle = throttle_seconds
        self._api = self._login()

    def _login(self) -> Garmin:
        try:
            api = Garmin()
            api.login(self._tokenstore)
            log.info("Logged in with saved tokens")
            return api
        except Exception as exc:
            log.info("Token login failed (%s) — authenticating with credentials", exc)
        api = Garmin(email=self._email, password=self._password)
        api.login(self._tokenstore)  # authenticates and saves tokens to tokenstore
        log.info("Logged in with credentials, tokens saved to %s", self._tokenstore)
        return api

    def _call(self, fn, *args):
        time.sleep(self._throttle)
        try:
            return fn(*args)
        except GarminConnectTooManyRequestsError:
            log.warning("Rate limited (429) — sleeping 60s and retrying once")
            time.sleep(60)
            return fn(*args)

    def get_daily_summary(self, day: date):
        return self._call(self._api.get_stats, day.isoformat())

    def get_sleep(self, day: date):
        return self._call(self._api.get_sleep_data, day.isoformat())

    def get_heart_rate(self, day: date):
        return self._call(self._api.get_heart_rates, day.isoformat())

    def get_stress(self, day: date):
        return self._call(self._api.get_stress_data, day.isoformat())

    def get_body_battery(self, day: date):
        return self._call(self._api.get_body_battery, day.isoformat())

    def get_respiration(self, day: date):
        return self._call(self._api.get_respiration_data, day.isoformat())

    def get_spo2(self, day: date):
        return self._call(self._api.get_spo2_data, day.isoformat())

    def get_steps(self, day: date):
        return self._call(self._api.get_steps_data, day.isoformat())

    def get_hrv(self, day: date):
        return self._call(self._api.get_hrv_data, day.isoformat())

    def get_training_status(self, day: date):
        return self._call(self._api.get_training_status, day.isoformat())

    def get_activities(self, start: int, limit: int):
        return self._call(self._api.get_activities, start, limit)

    def get_activity_splits(self, activity_id: int):
        return self._call(self._api.get_activity_splits, activity_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_garmin_client.py -v`
Expected: all PASS. Note: `GarminConnectTooManyRequestsError` import in tests requires `garminconnect` installed (Task 1 did this).

- [ ] **Step 5: Commit**

```bash
git add src/garmin_client.py tests/test_garmin_client.py
git commit -m "feat: Garmin client with token auth, throttle, 429 backoff"
```

---

### Task 12: Sync — plan_dates + sync_day

**Files:**
- Create: `src/sync.py`
- Test: `tests/test_sync.py`

- [ ] **Step 1: Write failing tests**

`tests/test_sync.py`:

```python
from datetime import date
from unittest.mock import MagicMock

import pytest

TODAY = date(2023, 11, 14)
START = date(2023, 11, 1)


# --- plan_dates ---

def test_plan_dates_today_first_then_backwards():
    from src.sync import plan_dates
    dates = plan_dates(synced=set(), today=TODAY, backfill_start=date(2023, 11, 11), max_days=10)
    assert dates == [TODAY, date(2023, 11, 13), date(2023, 11, 12), date(2023, 11, 11)]


def test_plan_dates_skips_synced_days():
    from src.sync import plan_dates
    dates = plan_dates(
        synced={date(2023, 11, 13), date(2023, 11, 11)},
        today=TODAY, backfill_start=date(2023, 11, 10), max_days=10,
    )
    assert dates == [TODAY, date(2023, 11, 12), date(2023, 11, 10)]


def test_plan_dates_today_always_included_even_if_synced():
    from src.sync import plan_dates
    dates = plan_dates(synced={TODAY}, today=TODAY, backfill_start=TODAY, max_days=10)
    assert dates == [TODAY]


def test_plan_dates_respects_max_days():
    from src.sync import plan_dates
    dates = plan_dates(synced=set(), today=TODAY, backfill_start=date(2023, 1, 1), max_days=3)
    assert dates == [TODAY, date(2023, 11, 13), date(2023, 11, 12)]


# --- sync_day ---

@pytest.fixture
def client():
    c = MagicMock()
    # all fetches return None → normalizers produce None/[] → nothing stored
    for m in ["get_daily_summary", "get_sleep", "get_heart_rate", "get_stress",
              "get_body_battery", "get_respiration", "get_spo2", "get_steps",
              "get_hrv", "get_training_status"]:
        getattr(c, m).return_value = None
    return c


@pytest.fixture
def db():
    return MagicMock()


def test_sync_day_fetches_all_metrics(client, db):
    from src.sync import sync_day
    ok = sync_day(client, db, TODAY)
    assert ok is True
    client.get_daily_summary.assert_called_once_with(TODAY)
    client.get_sleep.assert_called_once_with(TODAY)
    client.get_heart_rate.assert_called_once_with(TODAY)
    client.get_stress.assert_called_once_with(TODAY)
    client.get_body_battery.assert_called_once_with(TODAY)
    client.get_respiration.assert_called_once_with(TODAY)
    client.get_spo2.assert_called_once_with(TODAY)
    client.get_steps.assert_called_once_with(TODAY)
    client.get_hrv.assert_called_once_with(TODAY)
    client.get_training_status.assert_called_once_with(TODAY)


def test_sync_day_stores_normalized_rows(client, db):
    from src.sync import sync_day
    from tests.conftest import load_fixture
    client.get_daily_summary.return_value = load_fixture("daily_summary.json")
    client.get_heart_rate.return_value = load_fixture("heart_rate.json")
    sync_day(client, db, TODAY)
    assert db.upsert_daily_summary.call_args[0][0]["steps"] == 9543
    table, cols, rows = db.upsert_intraday.call_args_list[0][0]
    assert table == "hr_intraday"
    assert cols == ["bpm"]
    assert len(rows) == 2


def test_sync_day_metric_failure_returns_false_but_continues(client, db):
    from src.sync import sync_day
    client.get_sleep.side_effect = RuntimeError("API error")
    ok = sync_day(client, db, TODAY)
    assert ok is False
    client.get_training_status.assert_called_once()  # later metrics still ran


def test_sync_day_429_propagates(client, db):
    from garminconnect import GarminConnectTooManyRequestsError
    from src.sync import sync_day
    client.get_sleep.side_effect = GarminConnectTooManyRequestsError("429")
    with pytest.raises(GarminConnectTooManyRequestsError):
        sync_day(client, db, TODAY)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.sync'`.

- [ ] **Step 3: Write implementation**

`src/sync.py`:

```python
import logging
from datetime import date, timedelta

from garminconnect import GarminConnectTooManyRequestsError

from src import normalizers

log = logging.getLogger(__name__)

# (client method, normalizer, db upsert method)
DAILY_METRICS = [
    ("get_daily_summary", normalizers.normalize_daily_summary, "upsert_daily_summary"),
    ("get_sleep", normalizers.normalize_sleep, "upsert_sleep"),
    ("get_hrv", normalizers.normalize_hrv, "upsert_hrv"),
    ("get_training_status", normalizers.normalize_training_status, "upsert_training_status"),
]

# (client method, normalizer, table, value columns)
INTRADAY_METRICS = [
    ("get_heart_rate", normalizers.normalize_hr_intraday, "hr_intraday", ["bpm"]),
    ("get_stress", normalizers.normalize_stress_intraday, "stress_intraday", ["stress_level"]),
    ("get_body_battery", normalizers.normalize_body_battery_intraday, "body_battery_intraday", ["level"]),
    ("get_respiration", normalizers.normalize_respiration_intraday, "respiration_intraday", ["breaths_per_min"]),
    ("get_spo2", normalizers.normalize_spo2_intraday, "spo2_intraday", ["spo2_pct"]),
    ("get_steps", normalizers.normalize_steps_intraday, "steps_intraday", ["steps"]),
]


def plan_dates(synced: set, today: date, backfill_start: date, max_days: int) -> list[date]:
    """Today first, then unsynced days newest -> oldest, capped at max_days."""
    dates = [today]
    day = today - timedelta(days=1)
    while day >= backfill_start and len(dates) < max_days:
        if day not in synced:
            dates.append(day)
        day -= timedelta(days=1)
    return dates


def sync_day(client, db, day: date) -> bool:
    """Fetch, normalize and store every metric for one day. True if all succeeded."""
    ok = True
    for fetch_name, normalize, upsert_name in DAILY_METRICS:
        try:
            payload = getattr(client, fetch_name)(day)
            row = normalize(payload, day)
            if row:
                getattr(db, upsert_name)(row)
        except GarminConnectTooManyRequestsError:
            raise
        except Exception as exc:
            log.error("%s failed for %s: %s", fetch_name, day, exc)
            ok = False
    for fetch_name, normalize, table, value_cols in INTRADAY_METRICS:
        try:
            payload = getattr(client, fetch_name)(day)
            rows = normalize(payload, day)
            db.upsert_intraday(table, value_cols, rows)
        except GarminConnectTooManyRequestsError:
            raise
        except Exception as exc:
            log.error("%s failed for %s: %s", fetch_name, day, exc)
            ok = False
    return ok
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sync.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sync.py tests/test_sync.py
git commit -m "feat: date planning and single-day sync"
```

---

### Task 13: Sync — sync_wellness + sync_activities

**Files:**
- Modify: `src/sync.py`
- Test: `tests/test_sync.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_sync.py`)

```python
# --- sync_wellness ---

def test_sync_wellness_marks_past_days_but_not_today(client, db, mocker):
    from src import sync
    db.get_synced_dates.return_value = set()
    mocker.patch.object(sync, "sync_day", return_value=True)
    sync.sync_wellness(client, db, today=TODAY, backfill_start=date(2023, 11, 12), max_days=10)
    marked = [c[0][0] for c in db.mark_synced.call_args_list]
    assert marked == [date(2023, 11, 13), date(2023, 11, 12)]  # today NOT marked


def test_sync_wellness_does_not_mark_failed_days(client, db, mocker):
    from src import sync
    db.get_synced_dates.return_value = set()
    mocker.patch.object(sync, "sync_day", side_effect=[True, False, True])
    sync.sync_wellness(client, db, today=TODAY, backfill_start=date(2023, 11, 12), max_days=10)
    marked = [c[0][0] for c in db.mark_synced.call_args_list]
    assert marked == [date(2023, 11, 12)]  # today not marked; failed 13th not marked


# --- sync_activities ---

def test_sync_activities_upserts_new_activities_and_splits(client, db):
    from src.sync import sync_activities
    from tests.conftest import load_fixture
    db.get_latest_activity_start.return_value = None
    client.get_activities.side_effect = [load_fixture("activities.json"), []]
    client.get_activity_splits.return_value = load_fixture("activity_splits.json")
    sync_activities(client, db)
    assert db.upsert_activity.call_args[0][0]["activity_id"] == 12345678901
    client.get_activity_splits.assert_called_once_with(12345678901)
    assert len(db.upsert_activity_splits.call_args[0][0]) == 2


def test_sync_activities_stops_at_known_activity(client, db):
    from datetime import datetime, timezone
    from src.sync import sync_activities
    from tests.conftest import load_fixture
    # latest stored activity is NEWER than the fetched one -> nothing upserted
    db.get_latest_activity_start.return_value = datetime(2024, 1, 1, tzinfo=timezone.utc)
    client.get_activities.return_value = load_fixture("activities.json")
    sync_activities(client, db)
    db.upsert_activity.assert_not_called()


def test_sync_activities_empty_account(client, db):
    from src.sync import sync_activities
    db.get_latest_activity_start.return_value = None
    client.get_activities.return_value = []
    sync_activities(client, db)
    db.upsert_activity.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sync.py -v`
Expected: new tests FAIL — AttributeError/ImportError.

- [ ] **Step 3: Implement** (append to `src/sync.py`)

```python
def sync_wellness(client, db, today: date, backfill_start: date, max_days: int) -> None:
    dates = plan_dates(db.get_synced_dates(), today, backfill_start, max_days)
    log.info("Syncing %d wellness days (%s .. %s)", len(dates), dates[0], dates[-1])
    for day in dates:
        ok = sync_day(client, db, day)
        if ok and day != today:
            db.mark_synced(day)


def sync_activities(client, db, batch_size: int = 50) -> None:
    latest = db.get_latest_activity_start()
    start = 0
    while True:
        batch = client.get_activities(start, batch_size)
        if not batch:
            return
        for payload in batch:
            row = normalizers.normalize_activity(payload)
            if latest and row["start_time"] <= latest:
                return  # batches come newest-first; everything older is already stored
            db.upsert_activity(row)
            splits_payload = client.get_activity_splits(row["activity_id"])
            db.upsert_activity_splits(
                normalizers.normalize_activity_splits(splits_payload, row["activity_id"])
            )
        start += batch_size
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sync.py -v`
Expected: all PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sync.py tests/test_sync.py
git commit -m "feat: wellness range sync and activity sync"
```

---

### Task 14: Entrypoint + fixture validation script

**Files:**
- Create: `src/main.py`, `scripts/capture_fixtures.py`

- [ ] **Step 1: Write src/main.py**

```python
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from garminconnect import GarminConnectTooManyRequestsError

from src.db_client import GarminDB
from src.garmin_client import GarminClient
from src.sync import sync_activities, sync_wellness

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent.parent / "sql" / "schema.sql"


def run() -> None:
    db = GarminDB(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        database=os.environ["POSTGRES_DB"],
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
    db.create_tables(str(SCHEMA_PATH))

    client = GarminClient(
        email=os.environ["GARMIN_EMAIL"],
        password=os.environ["GARMIN_PASSWORD"],
        tokenstore=os.environ.get("GARMINTOKENS", "~/.garminconnect"),
        throttle_seconds=float(os.environ.get("THROTTLE_SECONDS", "1")),
    )

    today = date.today()
    backfill_start = date.fromisoformat(os.environ.get("BACKFILL_START", "2023-01-01"))
    max_days = int(os.environ.get("MAX_DAYS_PER_RUN", "50"))

    try:
        sync_wellness(client, db, today=today, backfill_start=backfill_start, max_days=max_days)
        sync_activities(client, db)
    except GarminConnectTooManyRequestsError:
        log.error("Aborted by rate limiting — will resume on next run")
        sys.exit(1)


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Write scripts/capture_fixtures.py**

Captures real API payloads to validate/refresh the synthetic fixtures. Strips nothing automatically — review before committing (payloads contain your Garmin user id / device id; fine for a private repo, sanitize if making public).

```python
"""Capture real Garmin API payloads into fixtures/captured/ for normalizer validation.

Usage: GARMIN_EMAIL=... GARMIN_PASSWORD=... python scripts/capture_fixtures.py [YYYY-MM-DD]
"""
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.garmin_client import GarminClient  # noqa: E402

load_dotenv()

OUT = Path(__file__).parent.parent / "fixtures" / "captured"
OUT.mkdir(parents=True, exist_ok=True)

day = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today() - timedelta(days=1)

client = GarminClient(
    email=os.environ["GARMIN_EMAIL"],
    password=os.environ["GARMIN_PASSWORD"],
    tokenstore=os.environ.get("GARMINTOKENS", "~/.garminconnect"),
)

ENDPOINTS = {
    "daily_summary": lambda: client.get_daily_summary(day),
    "sleep": lambda: client.get_sleep(day),
    "heart_rate": lambda: client.get_heart_rate(day),
    "stress": lambda: client.get_stress(day),
    "body_battery": lambda: client.get_body_battery(day),
    "respiration": lambda: client.get_respiration(day),
    "spo2": lambda: client.get_spo2(day),
    "steps": lambda: client.get_steps(day),
    "hrv": lambda: client.get_hrv(day),
    "training_status": lambda: client.get_training_status(day),
    "activities": lambda: client.get_activities(0, 5),
}

for name, fetch in ENDPOINTS.items():
    try:
        payload = fetch()
        (OUT / f"{name}.json").write_text(json.dumps(payload, indent=2, default=str))
        print(f"OK   {name}")
    except Exception as exc:
        print(f"FAIL {name}: {exc}")

acts = json.loads((OUT / "activities.json").read_text())
if acts:
    splits = client.get_activity_splits(acts[0]["activityId"])
    (OUT / "activity_splits.json").write_text(json.dumps(splits, indent=2, default=str))
    print("OK   activity_splits")
```

- [ ] **Step 3: Add fixtures/captured/ to .gitignore**

Append to `.gitignore`:

```
fixtures/captured/
```

- [ ] **Step 4: CHECKPOINT — ask the user to capture real payloads**

Ask the user to run (needs their real Garmin credentials, possibly MFA prompt):

```bash
GARMIN_EMAIL=... GARMIN_PASSWORD=... .venv/bin/python scripts/capture_fixtures.py
```

Then compare each `fixtures/captured/*.json` against the synthetic `fixtures/*.json` shapes used by the normalizers. Where keys differ (most likely `spo2.json`), update the synthetic fixture AND the normalizer, re-running the tests (red → green). This step validates the entire normalizer layer against reality.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/main.py scripts/capture_fixtures.py .gitignore
git commit -m "feat: entrypoint and fixture capture script"
```

---

### Task 15: Local end-to-end run

**Files:**
- Create: `.env.example`

- [ ] **Step 1: Create .env.example**

```
GARMIN_EMAIL=
GARMIN_PASSWORD=
GARMINTOKENS=.garminconnect
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=garmin
POSTGRES_USER=garmin
POSTGRES_PASSWORD=
BACKFILL_START=2023-01-01
MAX_DAYS_PER_RUN=50
THROTTLE_SECONDS=1
```

- [ ] **Step 2: CHECKPOINT — ask the user to run end-to-end**

User needs a reachable Postgres (the Pi one, or local Docker: `docker run -d -p 5432:5432 -e POSTGRES_DB=garmin -e POSTGRES_USER=garmin -e POSTGRES_PASSWORD=garmin postgres:16`). With `.env` filled in:

```bash
MAX_DAYS_PER_RUN=3 .venv/bin/python -m src.main
```

Expected: logs show login, "Syncing 3 wellness days", activity sync; then verify:

```sql
SELECT count(*) FROM hr_intraday;
SELECT * FROM sleep ORDER BY calendar_date DESC LIMIT 3;
SELECT calendar_date FROM sync_log ORDER BY calendar_date;
```

Today must NOT appear in `sync_log`; the two previous days must.

- [ ] **Step 3: Fix anything the real API breaks** (shape mismatches → update fixture + normalizer test-first), re-run suite.

- [ ] **Step 4: Commit**

```bash
git add .env.example
git commit -m "chore: env example"
```

---

### Task 16: Dockerfile + k8s manifests + README

**Files:**
- Create: `Dockerfile`, `k8s/cronjob.yaml`, `k8s/secret.example.yaml`, `k8s/pvc.yaml`
- Modify: `README.md`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY sql/ sql/

CMD ["python", "-m", "src.main"]
```

- [ ] **Step 2: Create k8s/pvc.yaml** (garth token persistence)

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: garmin-tokens
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 10Mi
```

- [ ] **Step 3: Create k8s/secret.example.yaml**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: garmin-sync-secrets
type: Opaque
stringData:
  GARMIN_EMAIL: "you@example.com"
  GARMIN_PASSWORD: "changeme"
  POSTGRES_HOST: "postgres"
  POSTGRES_PORT: "5432"
  POSTGRES_DB: "garmin"
  POSTGRES_USER: "garmin"
  POSTGRES_PASSWORD: "changeme"
```

- [ ] **Step 4: Create k8s/cronjob.yaml**

Image registry: match whatever `ticket-tracker-claude/k8s/` uses (check before writing; `localhost:32000/...` if MicroK8s built-in registry).

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: garmin-sync
spec:
  schedule: "30 5 * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: garmin-sync
              image: localhost:32000/garmin-data-db:latest
              envFrom:
                - secretRef:
                    name: garmin-sync-secrets
              env:
                - name: GARMINTOKENS
                  value: /tokens
                - name: BACKFILL_START
                  value: "2023-01-01"
                - name: MAX_DAYS_PER_RUN
                  value: "50"
                - name: THROTTLE_SECONDS
                  value: "1"
              volumeMounts:
                - name: tokens
                  mountPath: /tokens
          volumes:
            - name: tokens
              persistentVolumeClaim:
                claimName: garmin-tokens
```

- [ ] **Step 5: Update README.md** — describe pipeline, tables, env vars, local run, deploy steps (build image, push to Pi registry, `kubectl apply -f k8s/`).

- [ ] **Step 6: Run full suite one final time**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile k8s/ README.md
git commit -m "feat: Dockerfile, k8s manifests, README"
```

---

## Completion

After Task 16: use superpowers:finishing-a-development-branch — push `feat/garmin-sync`, open PR per repo hook convention.
