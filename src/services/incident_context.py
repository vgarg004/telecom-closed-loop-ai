from src.query.schemas import QueryFilters
from src.tools.kpi_tools import get_kpi_summary
from src.tools.alarm_tools import get_alarms
from src.tools.config_tools import get_configuration_changes
from src.tools.ticket_tools import get_tickets


def build_incident_context(filters: QueryFilters):
    """
    Build structured incident evidence from resolved query filters.
    """

    kpi_summary = get_kpi_summary(
        cell_id=filters.cell_id,
        start_time=filters.start_time,
        end_time=filters.end_time,
    )

    alarms = get_alarms(
        cell_id=filters.cell_id,
        site_id=filters.site_id,
        start_time=filters.start_time,
        end_time=filters.end_time,
        limit=100,
    )

    configuration_changes = get_configuration_changes(
        cell_id=filters.cell_id,
        site_id=filters.site_id,
        start_time=filters.start_time,
        end_time=filters.end_time,
        limit=100,
    )

    tickets = get_tickets(
        cell_id=filters.cell_id,
        start_time=filters.start_time,
        end_time=filters.end_time,
        limit=100,
    )

    return {
        "filters": filters.model_dump(),
        "kpi_summary": kpi_summary,
        "alarms": alarms,
        "configuration_changes": configuration_changes,
        "tickets": tickets,
    }