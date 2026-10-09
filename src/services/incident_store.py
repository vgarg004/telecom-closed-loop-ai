"""SQLite persistence for analyzed incidents and simulated action plans."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


class IncidentStore:
    def __init__(self, path="data/runtime/incidents.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def check_health(self):
        """Check database access and schema without modifying incident state."""
        with self._connect() as connection:
            connection.execute("SELECT incident_id FROM incidents LIMIT 1").fetchone()

    def _initialize(self):
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    cell_id TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    result_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS action_plans (
                    action_id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    approved_by TEXT,
                    plan_json TEXT NOT NULL,
                    result_json TEXT,
                    FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
                );

                CREATE INDEX IF NOT EXISTS idx_action_incident
                ON action_plans(incident_id, created_at);
                """
            )

    def save_incident(self, incident_id, request, result):
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO incidents (
                    incident_id, created_at, cell_id, start_time, end_time, result_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    _timestamp(),
                    request["cell_id"],
                    request["start_time"],
                    request["end_time"],
                    json.dumps(result, default=str),
                ),
            )

    def get_incident(self, incident_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "incident_id": row["incident_id"],
            "created_at": row["created_at"],
            "cell_id": row["cell_id"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "result": json.loads(row["result_json"]),
        }

    def save_action_plan(self, incident_id, action_result):
        plan = action_result["plan"]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO action_plans (
                    action_id, incident_id, created_at, status, plan_json, result_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    plan["action_id"],
                    incident_id,
                    _timestamp(),
                    action_result["status"],
                    json.dumps(plan, default=str),
                    json.dumps(action_result, default=str),
                ),
            )

    def get_action(self, action_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM action_plans WHERE action_id = ?", (action_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "action_id": row["action_id"],
            "incident_id": row["incident_id"],
            "created_at": row["created_at"],
            "status": row["status"],
            "approved_by": row["approved_by"],
            "plan": json.loads(row["plan_json"]),
            "result": json.loads(row["result_json"])
            if row["result_json"]
            else None,
        }

    def claim_action(self, action_id, approved_by):
        """Commit a single-winner claim before execution, across SQLite connections.

        Executing actions are never reclaimed automatically: a crash can leave
        execution outcome unknown and requires operator reconciliation.
        """
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE action_plans
                SET status = 'executing', approved_by = ?, result_json = NULL
                WHERE action_id = ? AND status = 'awaiting_approval'
                """,
                (approved_by, action_id),
            )
            claimed = cursor.rowcount == 1
        return claimed

    def complete_action(self, action_id, approved_by, action_result):
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE action_plans
                SET status = ?, approved_by = ?, result_json = ?
                WHERE action_id = ? AND status = 'executing'
                """,
                (
                    action_result["status"],
                    approved_by,
                    json.dumps(action_result, default=str),
                    action_id,
                ),
            )

    def list_actions(self, incident_id):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT action_id FROM action_plans
                WHERE incident_id = ? ORDER BY created_at
                """,
                (incident_id,),
            ).fetchall()
        return [self.get_action(row["action_id"]) for row in rows]
