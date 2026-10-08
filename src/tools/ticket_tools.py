from src.database.postgres import execute_query


def get_tickets(
    cell_id: str | None = None,
    priority: str | None = None,
    source: str | None = None,
    status: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 100,
):
    """
    Return tickets using optional filters.
    """

    conditions = []
    params = []

    if cell_id:
        conditions.append("cell_id = %s")
        params.append(cell_id)

    if priority:
        conditions.append("priority = %s")
        params.append(priority)

    if source:
        conditions.append("source = %s")
        params.append(source)

    if status:
        conditions.append("status = %s")
        params.append(status)

    if start_time:
        conditions.append("created_time >= %s")
        params.append(start_time)

    if end_time:
        conditions.append("created_time <= %s")
        params.append(end_time)

    where_clause = ""

    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = f"""
    SELECT
        ticket_id,
        created_time,
        cell_id,
        priority,
        source,
        issue_summary,
        status

    FROM tickets

    {where_clause}

    ORDER BY created_time DESC

    LIMIT %s;
    """

    params.append(limit)

    return execute_query(query, tuple(params))