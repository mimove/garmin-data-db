# garmin-data-db

Pulls wellness and activity data from Garmin Connect and stores it in PostgreSQL. A CronJob runs nightly on a Raspberry Pi 4 MicroK8s cluster, chips away at a configurable backfill window (newest-first, resumable), and keeps today's metrics fresh on every run.

```
Garmin Connect  →  garminconnect (garth token auth)  →  normalizers  →  PostgreSQL
```

## Features

- All wellness metrics: daily summary, resting HR, HRV, training status
- All intraday series (5-min): heart rate, stress, body battery, respiration, SpO2, steps
- Activities and per-activity lap/split data
- Newest-first resumable backfill — each run picks up where it left off
- Idempotent upserts — safe to re-run; today is always re-synced
- Rate-limit aware — 429 triggers a 60 s retry once, then exits cleanly so the next scheduled run resumes

## Data model

| Table | Contents |
|---|---|
| `daily_summary` | Steps, calories, resting HR, stress, intensity minutes, floors — one row per day |
| `sleep` | Sleep start/end, stages, score — one row per night (empty if watch not worn at night) |
| `hrv` | Nightly HRV summary — one row per night |
| `training_status` | Training status and load — one row per day |
| `intraday_heart_rate` | Heart-rate samples at 5-min resolution |
| `intraday_stress` | Stress level at 5-min resolution |
| `intraday_body_battery` | Body battery at 5-min resolution |
| `intraday_respiration` | Respiration rate at 5-min resolution |
| `intraday_spo2` | SpO2 at 5-min resolution (empty if watch not worn overnight) |
| `intraday_steps` | Step count at 5-min resolution |
| `activities` | One row per activity (sport, duration, distance, HR stats, …) |
| `activity_splits` | Lap/split records linked to `activities` |
| `sync_log` | Marks each calendar date as fully synced so backfill can skip it |

## Configuration

| Variable | Default | Description |
|---|---|---|
| `GARMIN_EMAIL` | — | Garmin Connect login e-mail |
| `GARMIN_PASSWORD` | — | Garmin Connect password |
| `GARMINTOKENS` | `~/.garminconnect` | Directory where garth stores OAuth tokens |
| `POSTGRES_HOST` | — | PostgreSQL hostname |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | — | Database name |
| `POSTGRES_USER` | — | Database user |
| `POSTGRES_PASSWORD` | — | Database password |
| `BACKFILL_START` | `2023-01-01` | Earliest date to backfill |
| `MAX_DAYS_PER_RUN` | `50` | Maximum calendar days processed per run |
| `THROTTLE_SECONDS` | `1` | Seconds to wait between Garmin API calls |

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy and edit environment variables
cp .env.example .env
# (edit .env with your credentials)

# Start a local PostgreSQL instance
docker run -d --name garmin-pg \
  -e POSTGRES_DB=garmin \
  -e POSTGRES_USER=garmin \
  -e POSTGRES_PASSWORD=garmin \
  -p 5432:5432 postgres:16

# Run a small backfill (3 days) to verify the pipeline
MAX_DAYS_PER_RUN=3 .venv/bin/python -m src.main

# Run the test suite (54 tests, no network or DB required)
python -m pytest tests/
```

## Deploy to Raspberry Pi 4 (MicroK8s / linux/arm64)

### 1. Build and push the image

```bash
docker buildx build --platform linux/arm64 \
  -t mimove/garmin-data-db:latest --push .
```

### 2. Apply manifests

```bash
kubectl apply -f k8s/namespace.yaml

# Copy the example secret, fill in real values, then apply.
# NEVER commit the file with real credentials.
cp k8s/secret.example.yaml k8s/secret.yaml
# (edit k8s/secret.yaml)
kubectl apply -f k8s/secret.yaml

kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/cronjob.yaml
```

The CronJob runs daily at 05:30 UTC (`schedule: "30 5 * * *"`), processes up to `MAX_DAYS_PER_RUN` days newest-first, and uses `concurrencyPolicy: Forbid` to prevent overlapping runs.

### 3. Initial Garmin token seed

Garmin uses OAuth tokens (stored by garth). The first authentication may require MFA. Tokens are persisted in the `garmin-tokens` PVC so subsequent runs authenticate silently.

Two options:

**Option A — let the first CronJob authenticate** (if your account does not require MFA on the Pi's IP): the job will authenticate with `GARMIN_EMAIL`/`GARMIN_PASSWORD` and save tokens to the PVC automatically.

**Option B — seed tokens from your local machine** (recommended if MFA is required):

```bash
# Run once locally to generate tokens
GARMINTOKENS=/tmp/garmin-tokens python -m src.main

# Copy tokens into the PVC via a temporary pod
kubectl run seed --image=busybox --restart=Never \
  --overrides='{"spec":{"volumes":[{"name":"t","persistentVolumeClaim":{"claimName":"garmin-tokens"}}],"containers":[{"name":"seed","image":"busybox","command":["sleep","3600"],"volumeMounts":[{"name":"t","mountPath":"/tokens"}]}]}}' \
  -n garmin
kubectl cp /tmp/garmin-tokens/. garmin/seed:/tokens/
kubectl delete pod seed -n garmin
```

## Fixture capture

`scripts/capture_fixtures.py` calls the live Garmin API and saves raw payloads to `fixtures/captured/` (gitignored). Use it to refresh test fixtures or inspect API responses:

```bash
python scripts/capture_fixtures.py
```

## Notes

- The `sleep` and `intraday_spo2` tables will be empty if the watch is not worn at night — this is expected.
- The `sync_log` table marks past days as fully synced; today is always re-synced regardless of the log so metrics stay current.
- On a 429 rate-limit error the client retries once after 60 seconds. A second 429 within the same run exits with code 1; the next scheduled CronJob resumes from where it left off.
