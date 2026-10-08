import psycopg


DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "telecom_db",
    "user": "telecom_user",
    "password": "telecom_password",
}


def main():

    conn = psycopg.connect(**DB_CONFIG)

    with conn.cursor() as cur:

        # ---------------------------------------------------
        # CELL INVENTORY
        # ---------------------------------------------------

        cur.execute("""
        CREATE TABLE IF NOT EXISTS cell_inventory (

            cell_id VARCHAR(50) PRIMARY KEY,
            site_id VARCHAR(50) NOT NULL,

            region VARCHAR(50),
            city VARCHAR(100),

            technology VARCHAR(20),
            band VARCHAR(20),

            bandwidth_mhz INTEGER,

            vendor VARCHAR(50),

            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,

            azimuth INTEGER,

            cell_status VARCHAR(30)
        );
        """)

        # ---------------------------------------------------
        # CELL KPI
        # ---------------------------------------------------

        cur.execute("""
        CREATE TABLE IF NOT EXISTS cell_kpi (

            timestamp TIMESTAMP NOT NULL,

            cell_id VARCHAR(50) NOT NULL,
            site_id VARCHAR(50),

            technology VARCHAR(20),

            dl_prb_utilization DOUBLE PRECISION,
            ul_prb_utilization DOUBLE PRECISION,

            rrc_setup_success_rate DOUBLE PRECISION,
            erab_setup_success_rate DOUBLE PRECISION,
            pdu_session_success_rate DOUBLE PRECISION,

            call_drop_rate DOUBLE PRECISION,
            handover_success_rate DOUBLE PRECISION,

            dl_throughput_mbps DOUBLE PRECISION,
            ul_throughput_mbps DOUBLE PRECISION,

            active_users INTEGER,

            availability_pct DOUBLE PRECISION,

            latency_ms DOUBLE PRECISION,
            packet_loss_pct DOUBLE PRECISION,

            rsrp_dbm DOUBLE PRECISION,
            sinr_db DOUBLE PRECISION
        );
        """)

        # ---------------------------------------------------
        # ALARMS
        # ---------------------------------------------------

        cur.execute("""
        CREATE TABLE IF NOT EXISTS alarms (

            alarm_id VARCHAR(50) PRIMARY KEY,

            timestamp TIMESTAMP NOT NULL,
            clear_time TIMESTAMP,

            cell_id VARCHAR(50),
            site_id VARCHAR(50),

            alarm_name VARCHAR(100),
            severity VARCHAR(30),

            status VARCHAR(30)
        );
        """)

        # ---------------------------------------------------
        # CONFIGURATION CHANGES
        # ---------------------------------------------------

        cur.execute("""
        CREATE TABLE IF NOT EXISTS configuration_changes (

            change_id VARCHAR(50) PRIMARY KEY,

            timestamp TIMESTAMP NOT NULL,

            cell_id VARCHAR(50),
            site_id VARCHAR(50),

            parameter_name VARCHAR(100),

            old_value DOUBLE PRECISION,
            new_value DOUBLE PRECISION,

            changed_by VARCHAR(100)
        );
        """)

        # ---------------------------------------------------
        # TICKETS
        # ---------------------------------------------------

        cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (

            ticket_id VARCHAR(50) PRIMARY KEY,

            created_time TIMESTAMP NOT NULL,

            cell_id VARCHAR(50),

            priority VARCHAR(20),
            source VARCHAR(50),

            issue_summary TEXT,

            status VARCHAR(30)
        );
        """)

        # ---------------------------------------------------
        # INDEXES
        # ---------------------------------------------------

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_kpi_cell_timestamp
        ON cell_kpi(cell_id, timestamp);
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_alarm_cell_timestamp
        ON alarms(cell_id, timestamp);
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_config_cell_timestamp
        ON configuration_changes(cell_id, timestamp);
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ticket_cell_time
        ON tickets(cell_id, created_time);
        """)

    conn.commit()

    conn.close()

    print("PostgreSQL schema created successfully.")


if __name__ == "__main__":
    main()