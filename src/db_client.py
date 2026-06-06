import psycopg2
import psycopg2.extras


class GarminDB:
    def __init__(self, host: str, port: int, database: str, username: str, password: str):
        try:
            self._conn = psycopg2.connect(
                host=host, port=port, dbname=database,
                user=username, password=password,
            )
        except psycopg2.Error as exc:
            raise RuntimeError(f"Cannot connect to PostgreSQL at {host}:{port} — {exc}") from exc

    def create_tables(self, schema_path: str) -> None:
        with open(schema_path) as f:
            sql = f.read()
        with self._conn.cursor() as cur:
            cur.execute(sql)
        self._conn.commit()

    def _upsert(self, table: str, pk_cols: list[str], row: dict) -> None:
        cols = list(row.keys())
        update_cols = [c for c in cols if c not in pk_cols]
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) "
            f"VALUES ({', '.join(['%s'] * len(cols))}) "
            f"ON CONFLICT ({', '.join(pk_cols)}) DO UPDATE SET "
            + ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        )
        params = [
            psycopg2.extras.Json(v) if isinstance(v, (dict, list)) else v
            for v in row.values()
        ]
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
        self._conn.commit()

    def upsert_daily_summary(self, row: dict) -> None:
        self._upsert("daily_summary", ["calendar_date"], row)

    def upsert_sleep(self, row: dict) -> None:
        self._upsert("sleep", ["calendar_date"], row)

    def upsert_hrv(self, row: dict) -> None:
        self._upsert("hrv", ["calendar_date"], row)

    def upsert_training_status(self, row: dict) -> None:
        self._upsert("training_status", ["calendar_date"], row)

    def upsert_activity(self, row: dict) -> None:
        self._upsert("activities", ["activity_id"], row)

    def upsert_intraday(self, table: str, value_cols: list[str], rows: list[dict]) -> None:
        if not rows:
            return
        cols = ["calendar_date", "ts"] + value_cols
        update = ", ".join(f"{c} = EXCLUDED.{c}" for c in value_cols)
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s "
            f"ON CONFLICT (calendar_date, ts) DO UPDATE SET {update}"
        )
        with self._conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, [tuple(r[c] for c in cols) for r in rows])
        self._conn.commit()

    def upsert_activity_splits(self, rows: list[dict]) -> None:
        if not rows:
            return
        cols = ["activity_id", "split_index", "distance_m", "duration_sec",
                "avg_hr", "avg_pace_s_per_km", "elevation_gain_m"]
        update = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols[2:])
        sql = (
            f"INSERT INTO activity_splits ({', '.join(cols)}) VALUES %s "
            f"ON CONFLICT (activity_id, split_index) DO UPDATE SET {update}"
        )
        with self._conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur, sql, [tuple(r.get(c) for c in cols) for r in rows]
            )
        self._conn.commit()

    def get_synced_dates(self) -> set:
        with self._conn.cursor() as cur:
            cur.execute("SELECT calendar_date FROM sync_log")
            return {r[0] for r in cur.fetchall()}

    def mark_synced(self, calendar_date) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sync_log (calendar_date) VALUES (%s) "
                "ON CONFLICT (calendar_date) DO NOTHING",
                (calendar_date,),
            )
        self._conn.commit()

    def get_activity_ids(self) -> set:
        with self._conn.cursor() as cur:
            cur.execute("SELECT activity_id FROM activities")
            return {r[0] for r in cur.fetchall()}
