import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from fastapi.testclient import TestClient
            from src.api.app import create_app
        except ImportError as error:
            raise unittest.SkipTest(f"API dependencies unavailable: {error}")

        cls.directory = TemporaryDirectory()
        root = Path(cls.directory.name)

        def understand(message):
            if "CELL_028_1" in message:
                return {
                    "cell_id": "CELL_028_1",
                    "site_id": None,
                    "start_time": "2026-08-05 07:00:00",
                    "end_time": "2026-08-05 10:00:00",
                }
            return {
                "cell_id": None,
                "site_id": None,
                "start_time": None,
                "end_time": None,
            }

        app = create_app(
            database_path=root / "incidents.db",
            audit_path=root / "audit.jsonl",
            api_key="test-key",
            query_understander=understand,
        )
        cls.client = TestClient(app)
        cls.headers = {"X-API-Key": "test-key"}

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.directory.cleanup()

    def test_health_is_public_and_api_requires_key(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/api/incidents/missing").status_code, 401)

    def test_analyze_plan_approve_and_idempotent_reapproval(self):
        analyzed = self.client.post(
            "/api/incidents",
            headers=self.headers,
            json={
                "cell_id": "CELL_028_1",
                "start_time": "2026-08-05 07:00:00",
                "end_time": "2026-08-05 10:00:00",
            },
        )
        self.assertEqual(analyzed.status_code, 200)
        incident = analyzed.json()
        self.assertEqual(incident["result"]["likely_cause"], "CONGESTION")

        planned = self.client.post(
            f"/api/incidents/{incident['incident_id']}/actions",
            headers=self.headers,
        )
        self.assertEqual(planned.status_code, 200)
        self.assertEqual(planned.json()["status"], "awaiting_approval")
        action_id = planned.json()["plan"]["action_id"]

        approved = self.client.post(
            f"/api/actions/{action_id}/approve",
            headers=self.headers,
            json={"approved_by": "api-test-operator"},
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "completed")

        repeated = self.client.post(
            f"/api/actions/{action_id}/approve",
            headers=self.headers,
            json={"approved_by": "api-test-operator"},
        )
        self.assertEqual(repeated.json(), approved.json())

    def test_chat_question_and_follow_up_reuse_incident_context(self):
        first = self.client.post(
            "/api/chat",
            headers=self.headers,
            json={
                "message": (
                    "What happened to CELL_028_1 between 2026-08-05 07:00:00 "
                    "and 2026-08-05 10:00:00?"
                )
            },
        )
        self.assertEqual(first.status_code, 200)
        self.assertIn("Congestion", first.json()["answer"])
        self.assertEqual(first.json()["filters"]["cell_id"], "CELL_028_1")

        follow_up = self.client.post(
            "/api/chat",
            headers=self.headers,
            json={
                "message": "What action do you recommend?",
                "incident_id": first.json()["incident_id"],
            },
        )
        self.assertEqual(follow_up.status_code, 200)
        self.assertEqual(follow_up.json()["result"]["likely_cause"], "CONGESTION")


if __name__ == "__main__":
    unittest.main()
