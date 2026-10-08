from src.tools.config_tools import get_configuration_changes


print("\nTEST 1: Changes for one cell")

result = get_configuration_changes(
    cell_id="CELL_017_3"
)

for row in result:
    print(row)


print("\nTEST 2: Recent handover-related changes")

result = get_configuration_changes(
    parameter_name="handover_margin_db",
    start_time="2026-08-01 00:00:00",
    end_time="2026-08-02 00:00:00",
    limit=20,
)

for row in result:
    print(row)