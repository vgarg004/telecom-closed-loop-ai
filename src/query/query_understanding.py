from src.query.parser import parse_query
from src.query.time_resolver import resolve_time_window


def understand_query(user_query: str):
    """
    Convert a natural-language telecom query into
    structured and resolved query filters.
    """

    parsed_filters = parse_query(user_query)

    resolved_filters = resolve_time_window(parsed_filters)

    return resolved_filters