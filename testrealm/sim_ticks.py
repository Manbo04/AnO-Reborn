"""Run H hourly ticks on the SIM db, no snapshots. Usage: python sim_ticks.py <hours>"""
import sys, os
assert "sim" in os.environ.get("PG_DATABASE", ""), "refusing: PG_DATABASE must contain 'sim'"
import tasks
from database import get_db_connection
H = int(sys.argv[1])
steps = [tasks.task_tax_income, tasks.task_generate_province_revenue, tasks.task_produce_unit_stockpiles, tasks.task_population_growth, tasks.task_loan_interest]
for h in range(1, H + 1):
    with get_db_connection() as c:
        c.cursor().execute("UPDATE task_runs SET last_run=NULL, last_period=NULL"); c.commit()
    for f in steps + ([tasks.task_manpower_increase] if h % 4 == 0 else []):
        try: f()
        except Exception as e: print("tick error", h, f.__name__, repr(e)[:100], flush=True)
print("ticks done", H)
