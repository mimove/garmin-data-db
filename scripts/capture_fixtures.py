"""Capture real Garmin API payloads into fixtures/captured/ for normalizer validation.

Usage: GARMIN_EMAIL=... GARMIN_PASSWORD=... python scripts/capture_fixtures.py [YYYY-MM-DD]
"""
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.garmin_client import GarminClient  # noqa: E402

load_dotenv()

OUT = Path(__file__).parent.parent / "fixtures" / "captured"
OUT.mkdir(parents=True, exist_ok=True)

day = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today() - timedelta(days=1)

client = GarminClient(
    email=os.environ["GARMIN_EMAIL"],
    password=os.environ["GARMIN_PASSWORD"],
    tokenstore=os.environ.get("GARMINTOKENS", "~/.garminconnect"),
)

ENDPOINTS = {
    "daily_summary": lambda: client.get_daily_summary(day),
    "sleep": lambda: client.get_sleep(day),
    "heart_rate": lambda: client.get_heart_rate(day),
    "stress": lambda: client.get_stress(day),
    "body_battery": lambda: client.get_body_battery(day),
    "respiration": lambda: client.get_respiration(day),
    "spo2": lambda: client.get_spo2(day),
    "steps": lambda: client.get_steps(day),
    "hrv": lambda: client.get_hrv(day),
    "training_status": lambda: client.get_training_status(day),
    "activities": lambda: client.get_activities(0, 5),
}

for name, fetch in ENDPOINTS.items():
    try:
        payload = fetch()
        (OUT / f"{name}.json").write_text(json.dumps(payload, indent=2, default=str))
        print(f"OK   {name}")
    except Exception as exc:
        print(f"FAIL {name}: {exc}")

acts = json.loads((OUT / "activities.json").read_text())
if acts:
    splits = client.get_activity_splits(acts[0]["activityId"])
    (OUT / "activity_splits.json").write_text(json.dumps(splits, indent=2, default=str))
    print("OK   activity_splits")
