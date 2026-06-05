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
