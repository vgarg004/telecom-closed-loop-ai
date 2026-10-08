from pathlib import Path
import psycopg

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "telecom_db",
    "user": "telecom_user",
    "password": "telecom_password",
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "telecom_data"

FILES = {
    "cell_inventory": "cell_inventory.csv",
    "cell_kpi": "cell_kpi.csv",
    "alarms": "alarms.csv",
    "configuration_changes": "configuration_changes.csv",
    "tickets": "tickets.csv",
}


def load_csv(cur, table_name, csv_path):
    print(f"Loading {csv_path.name} -> {table_name}")

    # Clear table first so re-running the script does not duplicate data
    cur.execute(f"TRUNCATE TABLE {table_name};")

    with open(csv_path, "r", encoding="utf-8") as f:
        with cur.copy(
            f"COPY {table_name} FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
        ) as copy:
            while data := f.read(1024 * 1024):
                copy.write(data)

    cur.execute(f"SELECT COUNT(*) FROM {table_name};")
    count = cur.fetchone()[0]

    print(f"Rows loaded: {count:,}")


def main():
    conn = psycopg.connect(**DB_CONFIG)

    try:
        with conn.cursor() as cur:
            for table_name, filename in FILES.items():
                csv_path = DATA_DIR / filename

                if not csv_path.exists():
                    raise FileNotFoundError(f"File not found: {csv_path}")

                load_csv(cur, table_name, csv_path)

        conn.commit()
        print("\nAll CSV files loaded successfully.")

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()