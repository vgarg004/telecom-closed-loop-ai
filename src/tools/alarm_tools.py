from src.database.postgres import execute_query


def get_alarms(
    cell_id: str | None = None,
    site_id: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 100,
):
    """
    Return alarms using optional filters.
    """

    conditions = []
    params = []

    if cell_id:
        conditions.append("cell_id = %s")
        params.append(cell_id)

    if site_id:
        conditions.append("site_id = %s")
        params.append(site_id)

    if severity:
        conditions.append("severity = %s")
        params.append(severity)

    if status:
        conditions.append("status = %s")
        params.append(status)

    if start_time:
        conditions.append("timestamp >= %s")
        params.append(start_time)

    if end_time:
        conditions.append("timestamp <= %s")
        params.append(end_time)

    where_clause = ""

    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = f"""
    SELECT
        alarm_id,
        timestamp,
        clear_time,
        cell_id,
        site_id,
        alarm_name,
        severity,
        status

    FROM alarms

    {where_clause}

    ORDER BY timestamp DESC

    LIMIT %s;
    """

    params.append(limit)

    return execute_query(query, tuple(params))