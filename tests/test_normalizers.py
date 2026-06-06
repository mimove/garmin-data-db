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
