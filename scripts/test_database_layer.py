from src.database.postgres import execute_query


query = """
SELECT
    cell_id,
    AVG(dl_prb_utilization) AS avg_dl_prb
FROM cell_kpi
GROUP BY cell_id
ORDER BY avg_dl_prb DESC
LIMIT 5;
"""

results = execute_query(query)

for row in results:
    print(row)