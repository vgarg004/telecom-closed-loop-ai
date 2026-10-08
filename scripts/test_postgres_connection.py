import psycopg

conn = psycopg.connect(
    host="localhost",
    port=5432,
    dbname="telecom_db",
    user="telecom_user",
    password="telecom_password"
)

print("PostgreSQL connection successful!")

conn.close()