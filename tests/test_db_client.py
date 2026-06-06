import pytest


@pytest.fixture
def db(mocker):
    mocker.patch("src.db_client.psycopg2.connect")
    from src.db_client import GarminDB
    return GarminDB(host="h", port=5432, database="d", username="u", password="p")


@pytest.fixture
def cur(db):
    return db._conn.cursor.return_value.__enter__.return_value


def test_connects_on_init(mocker):
    connect = mocker.patch("src.db_client.psycopg2.connect")
    from src.db_client import GarminDB
    GarminDB(host="h", port=5432, database="d", username="u", password="p")
    connect.assert_called_once_with(host="h", port=5432, dbname="d", user="u", password="p")


def test_connection_error_raises_runtime_error(mocker):
    import psycopg2
    mocker.patch("src.db_client.psycopg2.connect", side_effect=psycopg2.OperationalError("boom"))
    from src.db_client import GarminDB
    with pytest.raises(RuntimeError, match="Cannot connect"):
        GarminDB(host="h", port=5432, database="d", username="u", password="p")


def test_create_tables_executes_schema(db, cur, tmp_path):
    schema = tmp_path / "schema.sql"
    schema.write_text("CREATE TABLE IF NOT EXISTS x (id INT);")
    db.create_tables(str(schema))
    cur.execute.assert_called_once_with("CREATE TABLE IF NOT EXISTS x (id INT);")
    db._conn.commit.assert_called_once()


from datetime import date, datetime, timezone

DAY = date(2023, 11, 14)
TS = datetime(2023, 11, 14, 8, 0, tzinfo=timezone.utc)


def test_upsert_daily_summary_sql(db, cur):
    row = {"calendar_date": DAY, "steps": 100, "raw": {"a": 1}}
    db.upsert_daily_summary(row)
    sql, params = cur.execute.call_args[0]
    assert "INSERT INTO daily_summary" in sql
    assert "ON CONFLICT (calendar_date) DO UPDATE" in sql
    assert "steps = EXCLUDED.steps" in sql
    assert "raw = EXCLUDED.raw" in sql
    assert "calendar_date = EXCLUDED" not in sql  # PK not updated
    assert params[0] == DAY
    assert params[1] == 100
    import psycopg2.extras
    assert isinstance(params[2], psycopg2.extras.Json)  # dicts wrapped for JSONB
    db._conn.commit.assert_called_once()


def test_upsert_sleep_hrv_training_status_route_to_tables(db, cur):
    db.upsert_sleep({"calendar_date": DAY, "score": 80})
    db.upsert_hrv({"calendar_date": DAY, "status": "BALANCED"})
    db.upsert_training_status({"calendar_date": DAY, "vo2max": 54.0})
    sqls = [c[0][0] for c in cur.execute.call_args_list]
    assert "INSERT INTO sleep" in sqls[0]
    assert "INSERT INTO hrv" in sqls[1]
    assert "INSERT INTO training_status" in sqls[2]


def test_upsert_intraday_uses_execute_values(db, cur, mocker):
    ev = mocker.patch("src.db_client.psycopg2.extras.execute_values")
    rows = [{"calendar_date": DAY, "ts": TS, "bpm": 62}]
    db.upsert_intraday("hr_intraday", ["bpm"], rows)
    sql = ev.call_args[0][1]
    values = ev.call_args[0][2]
    assert "INSERT INTO hr_intraday (calendar_date, ts, bpm)" in sql
    assert "ON CONFLICT (calendar_date, ts) DO UPDATE" in sql
    assert values == [(DAY, TS, 62)]
    db._conn.commit.assert_called_once()


def test_upsert_intraday_no_rows_is_noop(db, cur, mocker):
    ev = mocker.patch("src.db_client.psycopg2.extras.execute_values")
    db.upsert_intraday("hr_intraday", ["bpm"], [])
    ev.assert_not_called()


def test_upsert_activity_and_splits(db, cur, mocker):
    ev = mocker.patch("src.db_client.psycopg2.extras.execute_values")
    db.upsert_activity({"activity_id": 1, "type": "running", "raw": {}})
    sql = cur.execute.call_args[0][0]
    assert "INSERT INTO activities" in sql
    assert "ON CONFLICT (activity_id) DO UPDATE" in sql

    db.upsert_activity_splits([
        {"activity_id": 1, "split_index": 0, "distance_m": 1000.0},
    ])
    sql = ev.call_args[0][1]
    assert "INSERT INTO activity_splits" in sql
    assert "ON CONFLICT (activity_id, split_index) DO UPDATE" in sql


def test_get_synced_dates(db, cur):
    cur.fetchall.return_value = [(date(2023, 11, 14),), (date(2023, 11, 13),)]
    result = db.get_synced_dates()
    assert result == {date(2023, 11, 14), date(2023, 11, 13)}
    assert "SELECT calendar_date FROM sync_log" in cur.execute.call_args[0][0]


def test_mark_synced(db, cur):
    db.mark_synced(DAY)
    sql, params = cur.execute.call_args[0]
    assert "INSERT INTO sync_log" in sql
    assert "ON CONFLICT (calendar_date) DO NOTHING" in sql
    assert params == (DAY,)
    db._conn.commit.assert_called_once()


def test_get_latest_activity_start(db, cur):
    cur.fetchone.return_value = (TS,)
    assert db.get_latest_activity_start() == TS
    assert "SELECT max(start_time) FROM activities" in cur.execute.call_args[0][0]


def test_get_latest_activity_start_empty_table(db, cur):
    cur.fetchone.return_value = (None,)
    assert db.get_latest_activity_start() is None
