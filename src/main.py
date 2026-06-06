import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from garminconnect import GarminConnectTooManyRequestsError

from src.db_client import GarminDB
from src.garmin_client import GarminClient
from src.sync import sync_activities, sync_wellness

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent.parent / "sql" / "schema.sql"


def run() -> None:
    db = GarminDB(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        database=os.environ["POSTGRES_DB"],
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
    db.create_tables(str(SCHEMA_PATH))

    client = GarminClient(
        email=os.environ["GARMIN_EMAIL"],
        password=os.environ["GARMIN_PASSWORD"],
        tokenstore=os.environ.get("GARMINTOKENS", "~/.garminconnect"),
        throttle_seconds=float(os.environ.get("THROTTLE_SECONDS", "1")),
    )

    today = date.today()
    backfill_start = date.fromisoformat(os.environ.get("BACKFILL_START", "2023-01-01"))
    max_days = int(os.environ.get("MAX_DAYS_PER_RUN", "50"))

    try:
        sync_wellness(client, db, today=today, backfill_start=backfill_start, max_days=max_days)
        sync_activities(client, db)
    except GarminConnectTooManyRequestsError:
        log.error("Aborted by rate limiting — will resume on next run")
        sys.exit(1)


if __name__ == "__main__":
    run()
