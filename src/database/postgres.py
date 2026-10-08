import os

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row


load_dotenv()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "telecom_db"),
    "user": os.getenv("POSTGRES_USER", "telecom_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "telecom_password"),
    "connect_timeout": 5,
}


def get_connection():
    return psycopg.connect(
        **DB_CONFIG,
        row_factory=dict_row
    )


def execute_query(query: str, params: tuple | None = None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)

            if cur.description is None:
                return []

            return cur.fetchall()