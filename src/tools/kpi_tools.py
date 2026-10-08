from src.database.postgres import execute_query


def get_kpi_summary(
    cell_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
):
    """
    Return KPI summary.

    Filters are optional:
    - cell_id only
    - time range only
    - both
    - neither
    """

    conditions = []
    params = []

    if cell_id:
        conditions.append("cell_id = %s")
        params.append(cell_id)

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
        cell_id,

        ROUND(AVG(dl_prb_utilization)::numeric, 2)
            AS avg_dl_prb_utilization,

        ROUND(AVG(ul_prb_utilization)::numeric, 2)
            AS avg_ul_prb_utilization,

        ROUND(AVG(call_drop_rate)::numeric, 2)
            AS avg_call_drop_rate,

        ROUND(AVG(handover_success_rate)::numeric, 2)
            AS avg_handover_success_rate,

        ROUND(AVG(dl_throughput_mbps)::numeric, 2)
            AS avg_dl_throughput_mbps,

        ROUND(AVG(latency_ms)::numeric, 2)
            AS avg_latency_ms,

        ROUND(AVG(packet_loss_pct)::numeric, 2)
            AS avg_packet_loss_pct,

        ROUND(AVG(rsrp_dbm)::numeric, 2)
            AS avg_rsrp_dbm,

        ROUND(AVG(sinr_db)::numeric, 2)
            AS avg_sinr_db

    FROM cell_kpi

    {where_clause}

    GROUP BY cell_id

    ORDER BY avg_dl_prb_utilization DESC;
    """

    return execute_query(query, tuple(params))