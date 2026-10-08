from src.tools.kpi_tools import get_kpi_summary


print("\nTEST 1: Cell + time range")

result = get_kpi_summary(
    cell_id="CELL_030_3",
    start_time="2026-08-01 00:00:00",
    end_time="2026-08-02 00:00:00",
)

for row in result:
    print(row)


print("\nTEST 2: Cell only")

result = get_kpi_summary(
    cell_id="CELL_030_3"
)

for row in result:
    print(row)


print("\nTEST 3: Time range only")

result = get_kpi_summary(
    start_time="2026-08-01 00:00:00",
    end_time="2026-08-01 03:00:00",
)

for row in result[:5]:
    print(row)