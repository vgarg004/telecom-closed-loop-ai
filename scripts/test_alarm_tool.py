from src.tools.alarm_tools import get_alarms


print("\nTEST 1: Alarms for one cell")

result = get_alarms(
    cell_id="CELL_010_2"
)

for row in result:
    print(row)


print("\nTEST 2: Critical alarms in a time window")

result = get_alarms(
    severity="WARNING",
    start_time="2026-08-01 00:00:00",
    end_time="2026-08-02 00:00:00",
    limit=20,
)

for row in result:
    print(row)