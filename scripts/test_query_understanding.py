from src.query.query_understanding import understand_query


queries = [
    "Show KPI for CELL_017_3 after 2026-08-01 10:00",

    "Show alarms for CELL_010_2 before 2026-08-02 15:00",

    "Investigate CELL_020_1 between 2026-08-01 10:00 and 2026-08-01 12:00",

    "What happened to CELL_030_3 around 2026-08-03 14:00?",
]


for query in queries:

    print("\n" + "=" * 80)

    print("USER QUERY:")
    print(query)

    result = understand_query(query)

    print("\nUNDERSTOOD QUERY:")
    print(result.model_dump())