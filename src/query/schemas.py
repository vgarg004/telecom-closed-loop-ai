from typing import Literal

from pydantic import BaseModel


TimeIntent = Literal[
    "between",
    "before",
    "after",
    "at",
    "around",
    "relative",
    "unspecified",
]


class QueryFilters(BaseModel):

    cell_id: str | None = None
    site_id: str | None = None

    start_time: str | None = None
    end_time: str | None = None

    point_time: str | None = None

    relative_hours: int | None = None

    time_intent: TimeIntent = "unspecified"

    original_query: str