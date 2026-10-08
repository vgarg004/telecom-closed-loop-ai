from src.database.postgres import execute_query


def get_configuration_changes(
    cell_id: str | None = None,
    site_id: str | None = None,
    parameter_name: str | None = None,
    changed_by: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 100,
):
    """
    Return configuration changes using optional filters.
    """

    conditions = []
    params = []

    if cell_id:
        conditions.append("cell_id = %s")
        params.append(cell_id)

    if site_id:
        conditions.append("site_id = %s")
        params.append(site_id)

    if parameter_name:
        conditions.append("parameter_name = %s")
        params.append(parameter_name)

    if changed_by:
        conditions.append("changed_by = %s")
        params.append(changed_by)

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
        change_id,
        timestamp,
        cell_id,
        site_id,
        parameter_name,
        old_value,
        new_value,
        changed_by

    FROM configuration_changes

    {where_clause}

    ORDER BY timestamp DESC

    LIMIT %s;
    """

    params.append(limit)

    return execute_query(query, tuple(params))