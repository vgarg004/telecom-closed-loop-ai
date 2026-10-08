import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd
from src.actions import run_action_loop
from src.analysis.incident import EvidenceStore, analyze_evidence, diagnose, collect_evidence
from src.workflows.assurance import build_assurance_graph


class AssuranceTests(unittest.TestCase):
    def test_empty_evidence_does_not_claim_cause(self):
        store = EvidenceStore()
        result = build_assurance_graph(store).invoke({"cell_id": "UNKNOWN", "start_time": "2026-08-01", "end_time": "2026-08-02"})["result"]
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNone(result["likely_cause"])

    def test_invalid_window(self):
        with self.assertRaises(ValueError):
            collect_evidence(None, "CELL_001_1", "2026-08-02", "2026-08-01")

    def test_active_alarm_overlap_and_end_exclusion(self):
        store = EvidenceStore.__new__(EvidenceStore)
        store.backend = "csv"
        store.frames = {"alarms": pd.DataFrame([
            {"cell_id": "C", "timestamp": pd.Timestamp("2026-08-01 09:00"), "clear_time": pd.Timestamp("2026-08-01 10:30")},
            {"cell_id": "C", "timestamp": pd.Timestamp("2026-08-01 11:00"), "clear_time": pd.NaT},
            {"cell_id": "C", "timestamp": pd.Timestamp("2026-08-01 08:00"), "clear_time": pd.Timestamp("2026-08-01 09:00")},
        ])}
        self.assertEqual(len(store.read("alarms", "C", datetime(2026, 8, 1, 10), datetime(2026, 8, 1, 11))), 1)

    def test_outage_precedes_secondary_symptoms(self):
        result = diagnose({"metrics": {"availability_pct": 0, "latency_ms": 100, "call_drop_rate": 10},
                           "changes": [], "start_time": "2026-08-01"})
        self.assertEqual(result["likely_cause"], "CELL_OUTAGE")

    def test_later_change_does_not_support_regression(self):
        result = diagnose({"metrics": {"call_drop_rate": 3}, "start_time": "2026-08-01 10:00",
                           "changes": [{"change_id": "CH1", "timestamp": "2026-08-01 10:30"}]})
        self.assertEqual(result["candidates"][0]["supporting_change_ids"], [])

    def test_supervisor_routes_only_available_evidence_agents(self):
        store = EvidenceStore()
        result = build_assurance_graph(store).invoke({
            "cell_id": "CELL_028_1",
            "start_time": "2026-08-05 07:00:00",
            "end_time": "2026-08-05 10:00:00",
        })["result"]
        self.assertEqual(
            result["orchestration"]["selected_agents"],
            ["kpi", "alarm", "ticket"],
        )
        self.assertEqual(
            result["orchestration"]["selected_agents"],
            result["orchestration"]["completed_agents"],
        )

    def test_alarm_onset_disambiguates_overlapping_scenarios(self):
        store = EvidenceStore()
        graph = build_assurance_graph(store)
        congestion = graph.invoke({
            "cell_id": "CELL_011_2",
            "start_time": "2026-08-09 09:00:00",
            "end_time": "2026-08-09 10:00:00",
        })["result"]
        regression = graph.invoke({
            "cell_id": "CELL_011_2",
            "start_time": "2026-08-09 08:00:00",
            "end_time": "2026-08-09 11:00:00",
        })["result"]
        self.assertEqual(congestion["likely_cause"], "CONGESTION")
        self.assertEqual(regression["likely_cause"], "CONFIGURATION_REGRESSION")

    def test_action_requires_approval_then_completes(self):
        rca = {
            "likely_cause": "CONGESTION",
            "analysis": {
                "cell_id": "CELL_001_1",
                "metrics": {"dl_prb_utilization": 96, "dl_throughput_mbps": 50},
            },
        }
        with TemporaryDirectory() as directory:
            audit = Path(directory) / "audit.jsonl"
            pending = run_action_loop(rca, audit_path=audit)
            completed = run_action_loop(
                rca,
                approved=True,
                approved_by="test-operator",
                audit_path=audit,
            )
            self.assertEqual(pending["status"], "awaiting_approval")
            self.assertEqual(completed["status"], "completed")
            self.assertTrue(completed["verification_passed"])
            self.assertGreaterEqual(len(audit.read_text().splitlines()), 6)

    def test_failed_action_verification_rolls_back(self):
        rca = {
            "likely_cause": "CELL_OUTAGE",
            "analysis": {
                "cell_id": "CELL_001_1",
                "metrics": {"availability_pct": 0},
            },
        }
        with TemporaryDirectory() as directory:
            result = run_action_loop(
                rca,
                approved=True,
                approved_by="test-operator",
                audit_path=Path(directory) / "audit.jsonl",
                force_verification_failure=True,
            )
        self.assertEqual(result["status"], "rolled_back")
        self.assertEqual(result["restored_metrics"], {"availability_pct": 0})


if __name__ == "__main__":
    unittest.main()
