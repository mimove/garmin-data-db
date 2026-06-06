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
