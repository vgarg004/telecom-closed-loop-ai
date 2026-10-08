from datetime import datetime

from src.query.schemas import QueryFilters
from src.query.time_resolver import resolve_time_window


print("\nTEST 1: Around")

filters = QueryFilters(
    cell_id="CELL_017_3",
    point_time="2026-08-01 14:00:00",
    time_intent="around",
    original_query="What happened around 2 PM?"
)

result = resolve_time_window(filters)

print(result.model_dump())


print("\nTEST 2: At")

filters = QueryFilters(
    cell_id="CELL_017_3",
    point_time="2026-08-01 14:00:00",
    time_intent="at",
    original_query="What happened at 2 PM?"
)

result = resolve_time_window(filters)

print(result.model_dump())


print("\nTEST 3: Last 2 hours")

filters = QueryFilters(
    cell_id="CELL_017_3",
    relative_hours=2,
    time_intent="relative",
    original_query="Show KPI for last 2 hours"
)

reference_time = datetime(
    2026,
    8,
    5,
    16,
    0,
    0,
)

result = resolve_time_window(
    filters,
    reference_time=reference_time,
)

print(result.model_dump())