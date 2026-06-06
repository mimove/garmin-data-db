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
