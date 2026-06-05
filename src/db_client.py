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
