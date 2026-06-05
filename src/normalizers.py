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
