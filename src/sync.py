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
