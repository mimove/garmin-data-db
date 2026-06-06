# Garmin Data Sync — Design

**Date:** 2026-06-05
**Status:** Approved

## Goal

Sync all health/sensor data from a Garmin Forerunner 965 (via Garmin Connect) into PostgreSQL, running as a daily Kubernetes CronJob on a Raspberry Pi 4. Backfill history to 2023-01-01, newest-first so recent data is queryable immediately.

## Decisions

| Decision | Choice |
|---|---|
| API access | `garminconnect` Python lib (unofficial, email/password + garth token persistence) |
| Scope | All metrics: daily wellness, sleep, HR/HRV, stress, body battery, SpO2, respiration, steps, training status, activities |
| Granularity | Daily summaries + intraday time series |
| Activities | Summaries + per-split laps (no GPS tracks / FIT streams) |
| Storage | PostgreSQL (new `garmin` database) on the Pi |
| Deployment | k8s CronJob, daily, same infra as ticket-tracker |
| Backfill | From 2023-01-01, newest → oldest, throttled, chipped away across runs |
| Architecture | Flat modules (ticket-tracker style), typed tables + raw JSONB safety column |
| Methodology | TDD with pytest, fixtures from real API responses, no network/DB in tests |

## Architecture

```
Garmin Connect API (garminconnect lib)
        │
   garmin_client.py      auth (garth tokens), raw API calls, throttling
        │
   normalizers.py        API JSON → typed row dicts (pure functions)
        │
   db_client.py          psycopg2, upserts, dedup by natural keys
        │
   sync.py               orchestrator: date range, fetch → normalize → store
        │
   main.py               entrypoint, env config, logging
```

### Modules

| File | Responsibility |
|---|---|
| `src/garmin_client.py` | Login via `garminconnect`. Persist garth tokens to `GARMINTOKENS` dir (k8s PVC) so runs reuse sessions instead of fresh logins. One method per endpoint: `get_sleep(date)`, `get_heart_rate(date)`, `get_stress(date)`, `get_body_battery(date)`, `get_steps(date)`, `get_spo2(date)`, `get_respiration(date)`, `get_hrv(date)`, `get_daily_summary(date)`, `get_activities(start, limit)`, `get_activity_splits(id)`, `get_training_status(date)`. Fixed `time.sleep(THROTTLE_SECONDS)` between calls. |
| `src/normalizers.py` | Pure functions, one per metric: raw JSON → list of row dicts. Testable without network. Empty/null API responses → `[]` (not an error). |
| `src/db_client.py` | Connection management, `upsert_*` per table (`ON CONFLICT DO UPDATE`), sync-state queries. Applies `sql/schema.sql` on startup if tables missing. |
| `src/sync.py` | `sync_day(date)` + `sync_range(...)`. Idempotent, re-run safe. Newest-first ordering. |
| `src/main.py` | Reads env config, runs sync, exit codes for k8s. |

## Data Model

Every table has a `raw JSONB` column with the original API payload — new fields can be backfilled later without re-calling the API (same pattern as ticket-tracker's `nutrition_raw_ocr`).

### Daily tables (PK: `calendar_date`)

| Table | Key columns |
|---|---|
| `daily_summary` | steps, calories_total, calories_active, floors, intensity_minutes_moderate, intensity_minutes_vigorous, resting_hr, min_hr, max_hr |
| `sleep` | score, duration_sec, deep_sec, light_sec, rem_sec, awake_sec, avg_spo2, avg_respiration, sleep_start (timestamptz), sleep_end (timestamptz) |
| `hrv` | last_night_avg_ms, status, weekly_avg_ms |
| `training_status` | vo2max, training_load_7d, status |

### Intraday tables (PK: `(calendar_date, ts)`, `ts` timestamptz)

| Table | Value columns |
|---|---|
| `hr_intraday` | bpm |
| `stress_intraday` | stress_level |
| `body_battery_intraday` | level |
| `respiration_intraday` | breaths_per_min |
| `spo2_intraday` | spo2_pct |
| `steps_intraday` | steps (15-min buckets) |

### Activities

| Table | PK | Key columns |
|---|---|---|
| `activities` | `activity_id` (Garmin's id) | type, name, start_time, distance_m, duration_sec, avg_hr, max_hr, avg_pace, calories, vo2max, aerobic_training_effect, anaerobic_training_effect |
| `activity_splits` | `(activity_id, split_index)` | distance_m, duration_sec, avg_hr, avg_pace, elevation_gain |

### Sync state

`sync_log(calendar_date PK, synced_at)` — one row per fully synced day. A day is marked only when all its metrics fetched and stored successfully. Today is never marked (data still arriving) and is always re-synced.

Schema lives in `sql/schema.sql`, applied idempotently on startup.

## Sync Flow

Per run (`main.py`):

1. **Login** — try saved garth tokens; fall back to email/password, save tokens.
2. **Wellness days** — sync **today first**, then walk **backwards** through unsynced days (newest → oldest) until `BACKFILL_START` (2023-01-01) reached or `MAX_DAYS_PER_RUN` (default 50) hit. "Next day to sync" = newest unsynced date. Recent data becomes queryable immediately; history fills over subsequent runs.
3. **Per day** — fetch each metric → normalize → upsert → insert `sync_log` row (unless today).
4. **Activities** — fetch list since last stored activity, upsert each + fetch and upsert its splits.

Throttling: ~12 API calls per day-synced, 1s sleep between calls. Full backfill (~880 days ≈ 10K calls) spread over ~18 daily runs at 50 days/run.

## Error Handling

| Failure | Behavior |
|---|---|
| Per-metric fetch error | Log, continue other metrics, day NOT marked synced (retried next run) |
| Auth failure | Abort run, non-zero exit (k8s surfaces CronJob failure) |
| HTTP 429 | Sleep 60s, retry once; second 429 aborts run (resumes next run) |
| Normalizer error on unexpected payload | Log with payload snippet, skip that metric for that day |
| No data for day (watch not worn, no sleep) | API returns empty/null → normalizer returns `[]` → no row, not an error |

## Configuration (env vars)

| Variable | Default | Description |
|---|---|---|
| `GARMIN_EMAIL` | — | Garmin Connect login |
| `GARMIN_PASSWORD` | — | Garmin Connect password (k8s Secret) |
| `GARMINTOKENS` | `~/.garminconnect` | garth token dir (PVC mount) |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | — | PostgreSQL connection |
| `BACKFILL_START` | `2023-01-01` | Oldest date to sync |
| `MAX_DAYS_PER_RUN` | `50` | Cap on wellness days per run |
| `THROTTLE_SECONDS` | `1` | Sleep between API calls |

## Testing (TDD)

- pytest; `tests/test_<module>.py` mirrors `src/`, shared `conftest.py`.
- `fixtures/` holds real anonymized API JSON per endpoint, captured once and sanitized.
- **normalizers** — bulk of tests: fixture in → expected rows out; edge cases (empty day, nulls, missing keys).
- **garmin_client** — mock `garminconnect.Garmin`: token reuse vs fresh login, throttle called, 429 backoff.
- **db_client** — mock cursor: assert upsert SQL + params.
- **sync** — mock client + db: newest-first ordering, today re-synced, failed metric leaves day unsynced, `MAX_DAYS_PER_RUN` respected.
- No network, no live DB in tests.

## Deployment

Dockerfile + k8s CronJob manifest + Secret (credentials) adapted from ticket-tracker. PVC for garth tokens. Built at the end, after the sync pipeline works locally.

## Out of Scope

- GPS track points / per-second FIT sensor streams
- Official Garmin Health API (OAuth)
- Weight/body composition (no compatible scale)
- Dashboards (Metabase queries the tables directly, separate concern)
