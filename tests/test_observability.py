import json
import logging
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from src.actions import run_action_loop
from src.api.app import create_app
from src.services.observability import JsonFormatter, request_id


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        root = Path(self.directory.name)
        self.app = create_app(database_path=root / "incidents.db",
                              audit_path=root / "audit.jsonl", api_key="secret-api-key")
        self.client = TestClient(self.app)
        self.headers = {"X-API-Key": "secret-api-key"}
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.client.close)

    def seed(self):
        incident_id = str(uuid4())
        rca = {"status": "investigation_required", "likely_cause": "CELL_OUTAGE",
               "analysis": {"cell_id": "TEST", "metrics": {"availability_pct": 0},
                            "tickets": [{"issue_summary": "sensitive ticket text"}]}}
        self.app.state.incidents.save_incident(incident_id, {
            "cell_id": "TEST", "start_time": "2026-08-01", "end_time": "2026-08-02",
        }, rca)
        return incident_id, rca

    def test_correlation_id_validation_and_context_isolation(self):
        supplied = str(uuid4())
        with self.assertLogs("telecom.observability", level="INFO") as logs:
            response = self.client.get("/health", headers={"X-Request-ID": supplied})
            self.assertEqual(response.headers["X-Request-ID"], supplied)
            for invalid in ("secret-api-key", "x" * 100, "", "bad id"):
                response = self.client.get("/health", headers={"X-Request-ID": invalid})
                self.assertEqual(str(UUID(response.headers["X-Request-ID"])), response.headers["X-Request-ID"])
                self.assertNotEqual(response.headers["X-Request-ID"], supplied)
        self.assertEqual(logs.records[0].correlation_id, supplied)
        self.assertEqual(len({record.correlation_id for record in logs.records}), 5)
        self.assertIsNone(request_id.get())

    def test_concurrent_request_context_isolated_in_worker_logs(self):
        barrier = Barrier(2)
        correlations = [str(uuid4()), str(uuid4())]
        graph = Mock()
        def invoke(payload):
            barrier.wait(timeout=10)
            return {"result": {"status": "insufficient_evidence", "likely_cause": None,
                               "analysis": {"cell_id": payload["cell_id"], "metrics": {}}}}
        graph.invoke.side_effect = invoke
        self.app.state.graphs[("csv", False)] = graph
        with self.assertLogs("telecom.observability", level="INFO") as logs, ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.client.post, "/api/incidents",
                                   headers={**self.headers, "X-Request-ID": correlation},
                                   json={"cell_id": "TEST", "start_time": "2026-08-01", "end_time": "2026-08-02"})
                       for correlation in correlations]
            responses = [future.result(timeout=10) for future in futures]
        for correlation, response in zip(correlations, responses):
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["X-Request-ID"], correlation)
            record = next(record for record in logs.records
                          if record.event == "incident.analysis" and record.correlation_id == correlation)
            self.assertEqual(record.incident_id, response.json()["incident_id"])

    def test_request_scoped_analysis_logs_redact_evidence_and_credentials(self):
        _, rca = self.seed()
        graph = Mock()
        graph.invoke.return_value = {"result": rca}
        self.app.state.graphs[("csv", False)] = graph
        supplied = str(uuid4())
        with self.assertLogs("telecom.observability", level="INFO") as logs:
            response = self.client.post("/api/incidents", headers={**self.headers, "X-Request-ID": supplied},
                                        json={"cell_id": "TEST", "start_time": "2026-08-01",
                                              "end_time": "2026-08-02"})
        self.assertEqual(response.status_code, 200)
        serialized = "\n".join(JsonFormatter().format(record) for record in logs.records)
        self.assertNotIn("secret-api-key", serialized)
        self.assertNotIn("sensitive ticket text", serialized)
        self.assertNotIn("availability_pct", serialized)
        with self.assertLogs("telecom.observability") as untrusted:
            self.client.get("/api/incidents/sensitive-ticket-text", headers=self.headers)
        self.assertNotIn("sensitive-ticket-text", JsonFormatter().format(untrusted.records[0]))
        analysis = next(json.loads(JsonFormatter().format(record)) for record in logs.records
                        if record.event == "incident.analysis")
        self.assertEqual(analysis["correlation_id"], supplied)
        self.assertEqual(analysis["incident_id"], response.json()["incident_id"])
        self.assertGreaterEqual(analysis["duration_ms"], 0)
        self.assertEqual(analysis["outcome"], "investigation_required")
        # The formatter must not fall back to unsafe message/exception formatting.
        record = logging.LogRecord("test", logging.ERROR, "", 0, "secret %s", ("ticket text",),
                                   (RuntimeError, RuntimeError("sensitive exception"), None))
        record.api_key = "secret-api-key"
        self.assertNotIn("secret", JsonFormatter().format(record))

    def test_metrics_auth_cardinality_and_independent_registration(self):
        self.assertEqual(self.client.get("/metrics").status_code, 401)
        self.assertEqual(self.client.get("/metrics", headers={"X-API-Key": "wrong"}).status_code, 401)
        for index in range(12):
            self.client.get(f"/api/incidents/random-{index}", headers=self.headers)
            self.client.get(f"/unknown-{index}")
        response = self.client.get("/metrics", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.headers["Content-Type"])
        samples = [sample for family in text_string_to_metric_families(response.text) for sample in family.samples]
        routes = {sample.labels["route"] for sample in samples if "route" in sample.labels}
        self.assertEqual(routes, {"/metrics", "/api/incidents/{incident_id}", "other"})
        self.assertNotIn("random-", response.text)
        self.assertNotIn("unknown-", response.text)
        for sample in samples:
            self.assertTrue(set(sample.labels).issubset({"method", "route", "status_class", "le", "stage", "outcome", "cause", "reason"}))
        other = create_app(database_path=Path(self.directory.name) / "other.db", api_key="secret-api-key")
        self.assertIsNot(other.state.telemetry.registry, self.app.state.telemetry.registry)
        with TestClient(other) as client:
            metrics = client.get("/metrics", headers=self.headers)
            self.assertEqual(metrics.status_code, 200)
            self.assertNotIn('route="/api/incidents/{incident_id}"', metrics.text)

    def test_action_lifecycle_logs_and_metrics_include_rollback(self):
        incident_id, _ = self.seed()
        supplied = str(uuid4())
        headers = {**self.headers, "X-Request-ID": supplied}
        with self.assertLogs("telecom.observability", level="INFO") as logs:
            planned = self.client.post(f"/api/incidents/{incident_id}/actions", headers=headers)
            action_id = planned.json()["plan"]["action_id"]
            def rollback(*args, **kwargs):
                return run_action_loop(*args, **kwargs, force_verification_failure=True)
            with patch("src.api.app.run_action_loop", side_effect=rollback):
                result = self.client.post(f"/api/actions/{action_id}/approve", headers=headers,
                                          json={"approved_by": "sensitive-operator"})
        self.assertEqual(result.json()["status"], "rolled_back")
        events = {record.event for record in logs.records}
        self.assertTrue({"action.planning", "action.claim", "action.simulation", "action.verification",
                         "action.rollback", "action.execution"}.issubset(events))
        for record in logs.records:
            self.assertEqual(record.correlation_id, supplied)
            if record.event.startswith("action."):
                self.assertEqual(record.incident_id, incident_id)
                self.assertEqual(record.action_id, action_id)
        rendered = "\n".join(JsonFormatter().format(record) for record in logs.records)
        self.assertNotIn("sensitive-operator", rendered)
        metrics = self.client.get("/metrics", headers=self.headers).text
        self.assertIn('telecom_action_outcomes_total{outcome="rolled_back",stage="execution"} 1.0', metrics)
        self.assertIn('telecom_action_outcomes_total{outcome="failed",stage="verification"} 1.0', metrics)

    def test_failure_and_approval_conflict_do_not_log_exception_text(self):
        incident_id, _ = self.seed()
        action_id = self.client.post(f"/api/incidents/{incident_id}/actions", headers=self.headers).json()["plan"]["action_id"]
        with self.assertLogs("telecom.observability", level="INFO") as logs, patch(
            "src.api.app.run_action_loop", side_effect=RuntimeError("secret-api-key sensitive ticket text"),
        ):
            failed = self.client.post(f"/api/actions/{action_id}/approve", headers=self.headers,
                                      json={"approved_by": "operator"})
        self.assertEqual(failed.status_code, 500)
        UUID(failed.headers["X-Request-ID"])
        self.assertNotIn("secret-api-key", "\n".join(JsonFormatter().format(record) for record in logs.records))
        conflict = self.client.post(f"/api/actions/{action_id}/approve", headers=self.headers,
                                    json={"approved_by": "operator"})
        self.assertEqual(conflict.status_code, 409)
        metrics = self.client.get("/metrics", headers=self.headers).text
        self.assertIn('telecom_approval_conflicts_total{reason="failed"} 1.0', metrics)
        self.assertIn('status_class="5xx"} 1.0', metrics)

    def test_instrumentation_failure_does_not_affect_business_or_claims(self):
        incident_id, _ = self.seed()
        with patch.object(self.app.state.telemetry, "record", side_effect=RuntimeError("telemetry")), patch(
            "src.services.observability.logger.log", side_effect=RuntimeError("logging"),
        ), patch.object(self.app.state.telemetry, "request", side_effect=RuntimeError("metrics")):
            planned = self.client.post(f"/api/incidents/{incident_id}/actions", headers=self.headers)
            action_id = planned.json()["plan"]["action_id"]
            result = self.client.post(f"/api/actions/{action_id}/approve", headers=self.headers,
                                      json={"approved_by": "operator"})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["status"], "completed")
        with patch("src.api.app.generate_latest", side_effect=RuntimeError("export")):
            self.assertEqual(self.client.get("/metrics", headers=self.headers).status_code, 503)
        with patch("src.services.observability.Counter", side_effect=RuntimeError("registration")):
            degraded = create_app(database_path=Path(self.directory.name) / "degraded.db")
        with TestClient(degraded) as client:
            self.assertEqual(client.get("/health").status_code, 200)

    def test_unexpected_http_failure_has_correlation_id_and_error_metric(self):
        with patch.object(self.app.state.incidents, "get_incident", side_effect=RuntimeError("private evidence")), self.assertLogs("telecom.observability") as logs:
            response = self.client.get(f"/api/incidents/{uuid4()}", headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assertIsNotNone(UUID(response.headers["X-Request-ID"]))
        self.assertNotIn("private evidence", "\n".join(JsonFormatter().format(record) for record in logs.records))
