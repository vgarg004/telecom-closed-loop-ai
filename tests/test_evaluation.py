import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.validate_scenarios import evaluate, main


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        # Tiny independent data fixture; bundled baselines are never written.
        pd.DataFrame([
            {"cell_id": "MARGINAL", "timestamp": "2026-08-01 10:00:00", "latency_ms": 41, "availability_pct": 100},
            {"cell_id": "OUTAGE", "timestamp": "2026-08-01 10:00:00", "latency_ms": 0, "availability_pct": 0},
        ]).to_csv(self.root / "cell_kpi.csv", index=False)
        pd.DataFrame(columns=["cell_id", "timestamp", "clear_time", "alarm_id", "alarm_name"]).to_csv(self.root / "alarms.csv", index=False)
        pd.DataFrame(columns=["cell_id", "timestamp", "change_id", "parameter_name"]).to_csv(self.root / "configuration_changes.csv", index=False)
        pd.DataFrame(columns=["cell_id", "created_time", "ticket_id", "issue_summary"]).to_csv(self.root / "tickets.csv", index=False)
        self.scenarios = self.root / "scenarios.csv"
        pd.DataFrame([
            {"scenario_id": "S1", "cell_id": "MARGINAL", "scenario_type": "TRANSPORT_DEGRADATION"},
            {"scenario_id": "S2", "cell_id": "OUTAGE", "scenario_type": "CELL_OUTAGE"},
            {"scenario_id": "S3", "cell_id": "MISSING", "scenario_type": "NO_CAUSE"},
            {"scenario_id": "S4", "cell_id": "MISSING", "scenario_type": ""},
        ]).assign(start_time="2026-08-01 10:00:00", end_time="2026-08-01 11:00:00").to_csv(self.scenarios, index=False)

    def hashes(self):
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.root.glob("*.csv")}

    def test_evaluation_output_accuracy_abstention_eligibility_and_identity(self):
        before = self.hashes()
        report = evaluate(self.root, self.scenarios)
        self.assertEqual(report["sample_count"], 4)
        metrics = report["metrics"]
        self.assertEqual(metrics["cause_accuracy"], {"labeled_samples": 2, "correct": 2, "accuracy": 1.0})
        self.assertEqual(metrics["abstention"]["count"], 2)
        self.assertEqual(metrics["abstention"]["insufficient_evidence_count"], 2)
        self.assertEqual(metrics["abstention"]["expected_abstention_rate"], 1.0)
        self.assertEqual(metrics["remediation"], {"eligible": 1, "eligibility_rate": .25, "rejected": 3, "rejection_rate": .75})
        self.assertEqual(report["dataset"]["label_source"], "synthetic")
        self.assertEqual(report["dataset"]["unlabeled_samples"], 1)
        latency = metrics["latency_ms"]
        self.assertTrue(0 <= latency["p50"] <= latency["p95"] <= latency["p99"])
        self.assertIn("python", report["environment"])
        self.assertEqual(report["dataset"]["identity_sha256"], evaluate(self.root, self.scenarios)["dataset"]["identity_sha256"])
        self.assertEqual(before, self.hashes())
        json.dumps(report, allow_nan=False)

    def test_label_provenance_is_explicit_and_unlabeled_accuracy_is_null(self):
        report = evaluate(self.root, self.scenarios, "ground_truth")
        self.assertEqual(report["dataset"]["label_source"], "ground_truth")
        report = evaluate(self.root, self.scenarios, "unlabeled")
        self.assertIsNone(report["metrics"]["cause_accuracy"]["accuracy"])
        self.assertEqual(report["metrics"]["cause_accuracy"]["labeled_samples"], 0)
        self.assertTrue(all(row["cause_correct"] is None for row in report["results"]))

    def test_cli_json_and_optional_legacy_csv_do_not_modify_inputs(self):
        before = self.hashes()
        output = self.root / "report.json"
        main(["--data-dir", str(self.root), "--scenarios", str(self.scenarios), "--output", str(output),
              "--validation-output", str(self.root / "validation" / "patterns.csv")])
        self.assertEqual(json.loads(output.read_text())["sample_count"], 4)
        self.assertEqual(len(pd.read_csv(self.root / "validation" / "patterns.csv")), 4)
        self.assertEqual(before, self.hashes())
        with self.assertRaises(SystemExit):
            main(["--data-dir", str(self.root), "--scenarios", str(self.scenarios), "--output", str(self.scenarios)])
        self.assertEqual(before, self.hashes())


class SafetyEvaluationTests(unittest.TestCase):
    def test_synthetic_negative_suite_rejects_unsafe_plans(self):
        root = Path('tests/fixtures/rca_safety')
        report = evaluate(root, root / 'scenarios.csv')
        self.assertEqual(report['dataset']['label_source'], 'synthetic')
        self.assertEqual(report['metrics']['safety']['forbidden_plan_samples'], 9)
        self.assertEqual(report['metrics']['safety']['unsafe_plans'], 0)
        self.assertEqual(report['metrics']['safety']['appropriate_abstention_or_rejection_rate'], 1)
        for row in report['results']:
            with self.subTest(case=row['scenario_id']):
                self.assertEqual(row['plan_eligible'], row['expected_plan'] == 'allowed')
        self.assertEqual(report['metrics']['cause_accuracy']['accuracy'], 1)

    def test_unlabeled_safety_expectations_are_not_scored(self):
        root = Path('tests/fixtures/rca_safety')
        report = evaluate(root, root / 'scenarios.csv', 'unlabeled')
        self.assertIsNone(report['metrics']['safety']['unsafe_plan_rate'])
        self.assertIsNone(report['metrics']['safety']['appropriate_abstention_or_rejection_rate'])
