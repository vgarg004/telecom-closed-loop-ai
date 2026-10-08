"""Validate injected evidence and evaluate the existing RCA/planning workflow offline."""

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

import pandas as pd

from src.actions import build_action_plan
from src.analysis.incident import CAUSES, EvidenceStore
from src.workflows.assurance import build_assurance_graph


def validate_patterns(data_dir, scenarios_path):
    """Retain the original synthetic KPI/event pattern checks, separate from RCA labels."""
    DATA_DIR = Path(data_dir)
    # Load data
    kpi = pd.read_csv(DATA_DIR / "cell_kpi.csv", parse_dates=["timestamp"])
    alarms = pd.read_csv(
        DATA_DIR / "alarms.csv",
        parse_dates=["timestamp", "clear_time"]
    )
    configs = pd.read_csv(
        DATA_DIR / "configuration_changes.csv",
        parse_dates=["timestamp"]
    )
    tickets = pd.read_csv(
        DATA_DIR / "tickets.csv",
        parse_dates=["created_time"]
    )
    scenarios = pd.read_csv(
        scenarios_path,
        parse_dates=["start_time", "end_time"]
    )

    results = []

    for _, s in scenarios.iterrows():

        cell_id = s["cell_id"]
        start = s["start_time"]
        end = s["end_time"]
        scenario_type = s["scenario_type"]

        # --------------------------------------------------
        # KPI evidence
        # --------------------------------------------------
        kpi_window = kpi[
            (kpi["cell_id"] == cell_id)
            & (kpi["timestamp"] >= start)
            & (kpi["timestamp"] < end)
        ]

        kpi_evidence = len(kpi_window) > 0

        # --------------------------------------------------
        # Alarm evidence
        # --------------------------------------------------
        alarm_window = alarms[
            (alarms["cell_id"] == cell_id)
            & (alarms["timestamp"] >= start)
            & (alarms["timestamp"] <= end)
        ]

        alarm_evidence = len(alarm_window) > 0

        # --------------------------------------------------
        # Configuration evidence
        # Look 2 hours before scenario start
        # --------------------------------------------------
        config_window = configs[
            (configs["cell_id"] == cell_id)
            & (configs["timestamp"] >= start - pd.Timedelta(hours=2))
            & (configs["timestamp"] <= start)
        ]

        config_evidence = len(config_window) > 0

        # --------------------------------------------------
        # Ticket evidence
        # Tickets can appear shortly after degradation starts
        # --------------------------------------------------
        ticket_window = tickets[
            (tickets["cell_id"] == cell_id)
            & (tickets["created_time"] >= start)
            & (tickets["created_time"] <= end + pd.Timedelta(hours=2))
        ]

        ticket_evidence = len(ticket_window) > 0

        # --------------------------------------------------
        # Simple KPI validation based on scenario type
        # --------------------------------------------------
        expected_kpi_pattern = False

        if not kpi_window.empty:

            if scenario_type == "CONGESTION":

                expected_kpi_pattern = (
                    kpi_window["dl_prb_utilization"].mean() > 85
                    and kpi_window["dl_throughput_mbps"].mean() > 0
                )

            elif scenario_type == "RADIO_INTERFERENCE":

                expected_kpi_pattern = (
                    kpi_window["sinr_db"].mean() < 12
                    or kpi_window["rsrp_dbm"].mean() < -95
                )

            elif scenario_type == "TRANSPORT_DEGRADATION":

                expected_kpi_pattern = (
                    kpi_window["latency_ms"].mean() > 40
                    or kpi_window["packet_loss_pct"].mean() > 1
                )

            elif scenario_type == "CELL_OUTAGE":

                expected_kpi_pattern = (
                    kpi_window["availability_pct"].mean() < 50
                )

            elif scenario_type == "CONFIGURATION_REGRESSION":

                expected_kpi_pattern = (
                    kpi_window["handover_success_rate"].mean() < 93
                    or kpi_window["call_drop_rate"].mean() > 2
                )

        results.append({
            "scenario_id": s["scenario_id"],
            "cell_id": cell_id,
            "scenario_type": scenario_type,
            "start_time": start,
            "end_time": end,
            "kpi_rows": len(kpi_window),
            "kpi_pattern_ok": expected_kpi_pattern,
            "alarm_found": alarm_evidence,
            "config_found": config_evidence,
            "ticket_found": ticket_evidence
        })
    return results


def evaluate(data_dir="data/telecom_data", scenarios_path=None, label_source="synthetic"):
    """Labels are supplied by the caller, never inferred from diagnostic KPIs.

    NO_CAUSE explicitly labels expected abstention. Blank labels are unlabelled.
    Eligibility is an observed planning decision, not a remediation correctness label.
    """
    data_dir = Path(data_dir)
    scenarios_path = Path(scenarios_path or data_dir / "evaluation" / "scenario_truth.csv")
    if label_source not in {"synthetic", "ground_truth", "unlabeled"}:
        raise ValueError("Unknown label source")
    scenarios = pd.read_csv(scenarios_path, keep_default_na=False)
    if scenarios.empty:
        raise ValueError("At least one scenario is required")
    required = {"scenario_id", "cell_id", "scenario_type", "start_time", "end_time"}
    if not required.issubset(scenarios.columns):
        raise ValueError("Scenario CSV is missing required columns")
    if scenarios.scenario_id.duplicated().any():
        raise ValueError("Scenario IDs must be unique")
    if label_source != "unlabeled":
        unknown = set(scenarios.scenario_type) - set(CAUSES) - {"", "NO_CAUSE"}
        if unknown:
            raise ValueError("Unsupported scenario labels")

    if "expected_plan" in scenarios and not set(scenarios.expected_plan).issubset({"", "allowed", "forbidden"}):
        raise ValueError("Unsupported expected_plan label")

    # Hash every actual input; no evidence content is copied into the report.
    inputs = {"scenarios": scenarios_path, **{name: data_dir / f"{name}.csv"
              for name in ("cell_kpi", "alarms", "configuration_changes", "tickets")}}
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
              for name, path in inputs.items()}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    patterns = validate_patterns(data_dir, scenarios_path)
    graph = build_assurance_graph(EvidenceStore("csv", data_dir))
    rows = []
    for scenario in scenarios.to_dict("records"):
        started = perf_counter()
        result = graph.invoke({key: scenario[key] for key in
                               ("cell_id", "start_time", "end_time")})["result"]
        eligible = build_action_plan(result) is not None
        latency_ms = (perf_counter() - started) * 1000
        expected = scenario["scenario_type"] if label_source != "unlabeled" else ""
        abstained = result["likely_cause"] is None
        rows.append({
            "scenario_id": scenario["scenario_id"],
            "case_category": scenario.get("case_category") or None,
            "expected_plan": scenario.get("expected_plan") if label_source != "unlabeled" else None,
            "expected_cause": expected or None,
            "predicted_cause": result["likely_cause"], "rca_status": result["status"],
            "cause_correct": result["likely_cause"] == expected if expected in CAUSES else None,
            "expected_abstention": expected == "NO_CAUSE" if expected else None,
            "abstained": abstained, "plan_eligible": eligible, "latency_ms": latency_ms,
        })
    count = len(rows)
    labeled = [row for row in rows if row["cause_correct"] is not None]
    correct = sum(row["cause_correct"] for row in labeled)
    abstentions = sum(row["abstained"] for row in rows)
    expected_abstentions = [row for row in rows if row["expected_abstention"] is True]
    unexpected_abstentions = sum(row["abstained"] for row in labeled)
    insufficient = sum(row["rca_status"] == "insufficient_evidence" for row in rows)
    eligible_count = sum(row["plan_eligible"] for row in rows)
    latencies = pd.Series([row["latency_ms"] for row in rows])
    source_root = Path(__file__).resolve().parents[1]
    source_hashes = {name: hashlib.sha256((source_root / name).read_bytes()).hexdigest()
                     for name in ("scripts/validate_scenarios.py", "src/analysis/incident.py",
                                  "src/actions/simulator.py", "src/workflows/assurance.py")}
    metrics = {
        "cause_accuracy": {"labeled_samples": len(labeled), "correct": correct,
                           "accuracy": correct / len(labeled) if labeled else None},
        "abstention": {"count": abstentions, "rate": abstentions / count,
                       "insufficient_evidence_count": insufficient,
                       "insufficient_evidence_rate": insufficient / count,
                       "expected_samples": len(expected_abstentions),
                       "expected_abstention_rate": (sum(row["abstained"] for row in expected_abstentions)
                                                    / len(expected_abstentions) if expected_abstentions else None),
                       "unexpected_labeled_abstentions": unexpected_abstentions},
        "remediation": {"eligible": eligible_count, "eligibility_rate": eligible_count / count,
                        "rejected": count - eligible_count, "rejection_rate": 1 - eligible_count / count},
        "latency_ms": {f"p{percentile}": float(latencies.quantile(percentile / 100))
                       for percentile in (50, 95, 99)},
        "pattern_validation": {key: sum(bool(row[key]) for row in patterns)
                               for key in ("kpi_pattern_ok", "alarm_found", "config_found", "ticket_found")},
    }
    forbidden = [row for row in rows if row["expected_plan"] == "forbidden"]
    unsafe = sum(row["plan_eligible"] for row in forbidden)
    metrics["safety"] = {
        "forbidden_plan_samples": len(forbidden), "unsafe_plans": unsafe,
        "unsafe_plan_rate": unsafe / len(forbidden) if forbidden else None,
        "appropriate_abstention_or_rejection_rate":
            sum(not row["plan_eligible"] for row in forbidden) / len(forbidden) if forbidden else None,
    }
    return {
        "schema_version": 2, "timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset": {"identity_sha256": identity, "input_sha256": hashes,
                    "label_source": label_source, "label_column": "scenario_type",
                    "unlabeled_samples": sum(row["expected_cause"] is None for row in rows)},
        "sample_count": count, "metrics": metrics, "results": rows,
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "dependencies": {name: version(name) for name in ("pandas", "numpy", "langgraph")},
                        "backend": "csv", "device": "cpu", "source_sha256": source_hashes},
        "methodology": {
            "latency": "One sequential pass; per-scenario collection, RCA and planning, excluding CSV load/graph construction; linear interpolated quantiles; no warmup.",
            "labels": "Bundled labels are synthetic injected-scenario expectations, not operator-confirmed production ground truth. ground_truth is caller-declared provenance.",
            "remediation": "Eligibility/rejection are policy decisions. Safety rates measure agreement with explicit forbidden-plan labels, not real-world safety or effectiveness; no actions execute.",
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/telecom_data")
    parser.add_argument("--scenarios", help="Scenario CSV; defaults to DATA_DIR/evaluation/scenario_truth.csv")
    parser.add_argument("--label-source", choices=("synthetic", "ground_truth", "unlabeled"), default="synthetic")
    parser.add_argument("--negative-data-dir", default="tests/fixtures/rca_safety",
                        help="Independent synthetic safety suite, always labeled synthetic")
    parser.add_argument("--output", default="data/runtime/scenario_evaluation.json")
    parser.add_argument("--validation-output", help="Optional original pattern-validation CSV output")
    args = parser.parse_args(argv)
    if args.validation_output and Path(args.output).resolve() == Path(args.validation_output).resolve():
        parser.error("JSON and CSV outputs must be different files")
    report = evaluate(args.data_dir, args.scenarios, args.label_source)
    safety_dir = Path(args.negative_data_dir)
    report["synthetic_safety_suite"] = evaluate(safety_dir, safety_dir / "scenarios.csv", "synthetic")
    destination = Path(args.output)
    input_paths = [Path(args.scenarios or Path(args.data_dir) / "evaluation/scenario_truth.csv")]
    input_paths += [Path(args.data_dir) / f"{name}.csv" for name in
                    ("cell_kpi", "alarms", "configuration_changes", "tickets")]
    input_paths += list(safety_dir.glob("*.csv"))
    for target in (args.output, args.validation_output):
        if target and Path(target).resolve() in {path.resolve() for path in input_paths}:
            parser.error("Output cannot overwrite an input dataset file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    if args.validation_output:
        path = Path(args.validation_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(validate_patterns(args.data_dir, input_paths[0])).to_csv(path, index=False)
    print(json.dumps({"sample_count": report["sample_count"], "label_source": args.label_source,
                      "metrics": report["metrics"],
                      "synthetic_safety_metrics": report["synthetic_safety_suite"]["metrics"]}, indent=2))


if __name__ == "__main__":
    main()
