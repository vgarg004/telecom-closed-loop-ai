import pandas as pd
from pathlib import Path

DATA_DIR = Path("data/telecom_data")
EVAL_DIR = DATA_DIR / "evaluation"

# Load data
kpi = pd.read_csv(DATA_DIR / "cell_kpi.csv", parse_dates=["timestamp"])
alarms = pd.read_csv(
    DATA_DIR / "alarms.csv",
    parse_dates=["timestamp", "clear_time"]
)
configs = pd.read_csv(
    DATA_DIR / "configuration_changes.csv",
    parse_dates=["timestamp"]
)
tickets = pd.read_csv(
    DATA_DIR / "tickets.csv",
    parse_dates=["created_time"]
)
scenarios = pd.read_csv(
    EVAL_DIR / "scenario_truth.csv",
    parse_dates=["start_time", "end_time"]
)

results = []

for _, s in scenarios.iterrows():

    cell_id = s["cell_id"]
    start = s["start_time"]
    end = s["end_time"]
    scenario_type = s["scenario_type"]

    # --------------------------------------------------
    # KPI evidence
    # --------------------------------------------------
    kpi_window = kpi[
        (kpi["cell_id"] == cell_id)
        & (kpi["timestamp"] >= start)
        & (kpi["timestamp"] < end)
    ]

    kpi_evidence = len(kpi_window) > 0

    # --------------------------------------------------
    # Alarm evidence
    # --------------------------------------------------
    alarm_window = alarms[
        (alarms["cell_id"] == cell_id)
        & (alarms["timestamp"] >= start)
        & (alarms["timestamp"] <= end)
    ]

    alarm_evidence = len(alarm_window) > 0

    # --------------------------------------------------
    # Configuration evidence
    # Look 2 hours before scenario start
    # --------------------------------------------------
    config_window = configs[
        (configs["cell_id"] == cell_id)
        & (configs["timestamp"] >= start - pd.Timedelta(hours=2))
        & (configs["timestamp"] <= start)
    ]

    config_evidence = len(config_window) > 0

    # --------------------------------------------------
    # Ticket evidence
    # Tickets can appear shortly after degradation starts
    # --------------------------------------------------
    ticket_window = tickets[
        (tickets["cell_id"] == cell_id)
        & (tickets["created_time"] >= start)
        & (tickets["created_time"] <= end + pd.Timedelta(hours=2))
    ]

    ticket_evidence = len(ticket_window) > 0

    # --------------------------------------------------
    # Simple KPI validation based on scenario type
    # --------------------------------------------------
    expected_kpi_pattern = False

    if not kpi_window.empty:

        if scenario_type == "CONGESTION":

            expected_kpi_pattern = (
                kpi_window["dl_prb_utilization"].mean() > 85
                and kpi_window["dl_throughput_mbps"].mean() > 0
            )

        elif scenario_type == "RADIO_INTERFERENCE":

            expected_kpi_pattern = (
                kpi_window["sinr_db"].mean() < 12
                or kpi_window["rsrp_dbm"].mean() < -95
            )

        elif scenario_type == "TRANSPORT_DEGRADATION":

            expected_kpi_pattern = (
                kpi_window["latency_ms"].mean() > 40
                or kpi_window["packet_loss_pct"].mean() > 1
            )

        elif scenario_type == "CELL_OUTAGE":

            expected_kpi_pattern = (
                kpi_window["availability_pct"].mean() < 50
            )

        elif scenario_type == "CONFIGURATION_REGRESSION":

            expected_kpi_pattern = (
                kpi_window["handover_success_rate"].mean() < 93
                or kpi_window["call_drop_rate"].mean() > 2
            )

    results.append({
        "scenario_id": s["scenario_id"],
        "cell_id": cell_id,
        "scenario_type": scenario_type,
        "start_time": start,
        "end_time": end,
        "kpi_rows": len(kpi_window),
        "kpi_pattern_ok": expected_kpi_pattern,
        "alarm_found": alarm_evidence,
        "config_found": config_evidence,
        "ticket_found": ticket_evidence
    })


result_df = pd.DataFrame(results)

result_df.to_csv(
    EVAL_DIR / "scenario_validation_report.csv",
    index=False
)

print("\nScenario validation completed.\n")

print(result_df.head(20))

print("\n-----------------------------------")
print("VALIDATION SUMMARY")
print("-----------------------------------")

print(
    "Total scenarios:",
    len(result_df)
)

print(
    "KPI pattern OK:",
    result_df["kpi_pattern_ok"].sum()
)

print(
    "Alarm found:",
    result_df["alarm_found"].sum()
)

print(
    "Config found:",
    result_df["config_found"].sum()
)

print(
    "Ticket found:",
    result_df["ticket_found"].sum()
)

print("-----------------------------------")