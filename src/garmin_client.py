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
