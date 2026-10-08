from dotenv import load_dotenv

load_dotenv()
from langchain_openai import ChatOpenAI

from src.query.schemas import QueryFilters


llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
)


structured_llm = llm.with_structured_output(QueryFilters)


SYSTEM_PROMPT = """
You extract telecom query filters from user questions.

Extract:

- cell_id
- site_id
- start_time
- end_time
- point_time
- relative_hours
- time_intent
- original_query

Allowed time_intent values:

between
before
after
at
around
relative
unspecified

Rules:

"after", "from", "since"
-> time_intent = "after"
-> put the resolved timestamp in start_time

"before", "until", "up to"
-> time_intent = "before"
-> put the resolved timestamp in end_time

"between X and Y"
-> time_intent = "between"
-> start_time = X
-> end_time = Y

"at X"
-> time_intent = "at"
-> point_time = X

"around X"
-> time_intent = "around"
-> point_time = X

"last N hours", "previous N hours"
-> time_intent = "relative"
-> relative_hours = N

Do not invent start/end windows for "at" or "around".
Those windows will be created later by deterministic Python code.

Return timestamps in:
YYYY-MM-DD HH:MM:SS

If something is unclear, return None rather than guessing.
"""


def parse_query(user_query: str) -> QueryFilters:

    messages = [
        (
            "system",
            SYSTEM_PROMPT,
        ),
        (
            "human",
            user_query,
        ),
    ]

    result = structured_llm.invoke(messages)

    return result