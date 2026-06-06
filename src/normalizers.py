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
