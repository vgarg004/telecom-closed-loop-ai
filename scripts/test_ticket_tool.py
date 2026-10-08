from src.tools.ticket_tools import get_tickets


print("\nTEST 1: Tickets for one cell")

result = get_tickets(
    cell_id="CELL_008_3"
)

for row in result:
    print(row)


print("\nTEST 2: Priority P2 tickets in a time window")

result = get_tickets(
    priority="P2",
    start_time="2026-08-01 00:00:00",
    end_time="2026-08-02 00:00:00",
    limit=20,
)

for row in result:
    print(row)