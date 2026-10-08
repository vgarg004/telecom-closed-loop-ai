from pprint import pprint

from src.services.incident_context import build_incident_context


context = build_incident_context(
    cell_id="CELL_017_3",
    start_time="2026-08-01 00:00:00",
    end_time="2026-08-02 00:00:00",
)

pprint(context)