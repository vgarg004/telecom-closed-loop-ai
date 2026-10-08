from pprint import pprint

from src.query.query_understanding import understand_query
from src.services.incident_context import build_incident_context


user_query = (
    "What happened to CELL_030_3 "
    "around 2026-08-03 14:00?"
)

filters = understand_query(user_query)

context = build_incident_context(filters)

pprint(context)