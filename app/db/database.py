import os
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv

load_dotenv()

_db_pool: pooling.MySQLConnectionPool | None = None


def _get_or_create_pool() -> pooling.MySQLConnectionPool:
    """Lazily initializes the MySQL connection pool on first database access."""
    global _db_pool
    if _db_pool is None:
        _db_pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="ops_pool",
            pool_size=5,
            pool_reset_session=True,
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            database=os.getenv("DB_NAME"),
        )
    return _db_pool


def get_db_connection(read_only: bool = False):
    """
    Borrows a MySQL connection from the pool.
    When read_only=True, enforces a session-level READ ONLY transaction guard
    so autonomous lookup tools cannot mutate state.
    """
    try:
        conn = _get_or_create_pool().get_connection()
        cursor = conn.cursor()
        if read_only:
            cursor.execute("SET SESSION TRANSACTION READ ONLY;")
        else:
            cursor.execute("SET SESSION TRANSACTION READ WRITE;")
            conn.autocommit = False
        cursor.close()
        return conn
    except mysql.connector.Error as err:
        raise RuntimeError(f"Database connection pool error: {err}") from err