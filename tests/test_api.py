import unittest
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from threading import Barrier, Event
from unittest.mock import patch
from uuid import uuid4
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

    def test_concurrent_approval_executes_once_and_persists_terminal_state(self):
        from fastapi.testclient import TestClient
        from src.actions import run_action_loop
        from src.api.app import create_app
        from src.services.incident_store import IncidentStore

        for terminal_status in ("completed", "rolled_back", "failed"):
            with self.subTest(status=terminal_status), TemporaryDirectory() as directory:
                root = Path(directory)
                apps = [create_app(database_path=root / "incidents.db",
                                   audit_path=root / "audit.jsonl", api_key="test-key")
                        for _ in range(2)]
                store = apps[0].state.incidents
                incident_id = str(uuid4())
                rca = {"likely_cause": "CELL_OUTAGE", "analysis": {
                    "cell_id": "TEST", "metrics": {"availability_pct": 0},
                }}
                store.save_incident(incident_id, {
                    "cell_id": "TEST", "start_time": "2026-08-01",
                    "end_time": "2026-08-02",
                }, rca)
                pending = run_action_loop(rca, audit_path=None)
                store.save_action_plan(incident_id, pending)
                action_id = pending["plan"]["action_id"]
                url = f"/api/actions/{action_id}/approve"
                barrier = Barrier(2)
                executing = Event()
                release = Event()
                original_claim = IncidentStore.claim_action

                def claim(instance, action_id, approved_by):
                    barrier.wait(timeout=10)
                    return original_claim(instance, action_id, approved_by)

                def execute(*args, **kwargs):
                    executing.set()
                    if not release.wait(timeout=10):
                        raise TimeoutError("Test did not release action execution")
                    if terminal_status == "failed":
                        raise RuntimeError("Injected execution failure")
                    return run_action_loop(
                        *args, **kwargs,
                        force_verification_failure=terminal_status == "rolled_back",
                    )

                with TestClient(apps[0]) as first, TestClient(apps[1]) as second:
                    with patch.object(IncidentStore, "claim_action", claim), patch(
                        "src.api.app.run_action_loop", side_effect=execute,
                    ) as runner, ThreadPoolExecutor(max_workers=2) as pool:
                        futures = {
                            pool.submit(client.post, url, headers=self.headers,
                                        json={"approved_by": operator}): operator
                            for client, operator in ((first, "operator-1"), (second, "operator-2"))
                        }
                        try:
                            self.assertTrue(executing.wait(timeout=10))
                            done, waiting = wait(futures, timeout=10, return_when=FIRST_COMPLETED)
                            self.assertEqual(len(done), 1)
                            conflict = next(iter(done)).result()
                            self.assertEqual(conflict.status_code, 409)
                            self.assertEqual(conflict.json()["detail"], "Action is already executing")
                            in_progress = apps[1].state.incidents.get_action(action_id)
                            self.assertEqual(in_progress["status"], "executing")
                            self.assertIsNone(in_progress["result"])
                        finally:
                            release.set()
                        responses = {future: future.result(timeout=10) for future in futures}
                        self.assertEqual(runner.call_count, 1)

                    winner = next(future for future, response in responses.items()
                                  if response.status_code != 409)
                    response = responses[winner]
                    self.assertEqual(response.status_code, 500 if terminal_status == "failed" else 200)
                    # Reopening the database verifies committed state, not an app cache.
                    saved = IncidentStore(root / "incidents.db").get_action(action_id)
                    self.assertEqual(saved["status"], terminal_status)
                    self.assertEqual(saved["result"]["status"], terminal_status)
                    self.assertEqual(saved["approved_by"], futures[winner])
                    self.assertEqual(saved["plan"], pending["plan"])
                    with patch("src.api.app.run_action_loop") as runner:
                        repeated = second.post(url, headers=self.headers,
                                               json={"approved_by": "another-operator"})
                        runner.assert_not_called()
                    if terminal_status == "failed":
                        self.assertEqual(repeated.status_code, 409)
                    else:
                        self.assertEqual(saved["result"], response.json())
                        self.assertEqual(repeated.status_code, 200)
                        self.assertEqual(repeated.json(), response.json())
                    self.assertEqual(IncidentStore(root / "incidents.db").get_action(action_id), saved)

    def test_executing_action_is_not_reclaimed_after_restart(self):
        from fastapi.testclient import TestClient
        from src.actions import run_action_loop
        from src.api.app import create_app
        from src.services.incident_store import IncidentStore

        with TemporaryDirectory() as directory:
            path = Path(directory) / "incidents.db"
            store = IncidentStore(path)
            rca = {"likely_cause": "CELL_OUTAGE", "analysis": {
                "cell_id": "TEST", "metrics": {"availability_pct": 0},
            }}
            pending = run_action_loop(rca, audit_path=None)
            store.save_action_plan("incident", pending)
            action_id = pending["plan"]["action_id"]
            self.assertTrue(store.claim_action(action_id, "original-operator"))
            app = create_app(database_path=path, api_key="test-key")
            with TestClient(app) as client, patch("src.api.app.run_action_loop") as runner:
                response = client.post(f"/api/actions/{action_id}/approve",
                                       headers=self.headers, json={"approved_by": "new-operator"})
                self.assertEqual(response.status_code, 409)
                runner.assert_not_called()
            saved = IncidentStore(path).get_action(action_id)
            self.assertEqual(saved["status"], "executing")
            self.assertEqual(saved["approved_by"], "original-operator")
            self.assertIsNone(saved["result"])

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
