from datetime import datetime, timedelta

from src.query.schemas import QueryFilters


def resolve_time_window(
    filters: QueryFilters,
    reference_time: datetime | None = None,
) -> QueryFilters:

    if reference_time is None:
        reference_time = datetime.now()

    # -----------------------------------
    # AT
    # -----------------------------------

    if filters.time_intent == "at" and filters.point_time:

        point = datetime.fromisoformat(filters.point_time)

        # 15 minutes before and after
        filters.start_time = (
            point - timedelta(minutes=15)
        ).strftime("%Y-%m-%d %H:%M:%S")

        filters.end_time = (
            point + timedelta(minutes=15)
        ).strftime("%Y-%m-%d %H:%M:%S")

    # -----------------------------------
    # AROUND
    # -----------------------------------

    elif filters.time_intent == "around" and filters.point_time:

        point = datetime.fromisoformat(filters.point_time)

        # 30 minutes before and after
        filters.start_time = (
            point - timedelta(minutes=30)
        ).strftime("%Y-%m-%d %H:%M:%S")

        filters.end_time = (
            point + timedelta(minutes=30)
        ).strftime("%Y-%m-%d %H:%M:%S")

    # -----------------------------------
    # RELATIVE
    # -----------------------------------

    elif (
        filters.time_intent == "relative"
        and filters.relative_hours
    ):

        filters.end_time = reference_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        filters.start_time = (
            reference_time
            - timedelta(hours=filters.relative_hours)
        ).strftime("%Y-%m-%d %H:%M:%S")

    return filters