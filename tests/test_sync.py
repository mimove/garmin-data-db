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
