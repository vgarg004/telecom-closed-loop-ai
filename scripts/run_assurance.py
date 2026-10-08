"""Run one incident or evaluate heuristic RCA against the supplied scenario truth."""
import argparse
import json
from pathlib import Path
import pandas as pd
from src.analysis.incident import EvidenceStore
from src.actions import run_action_loop
from src.workflows.assurance import build_assurance_graph


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["csv", "postgres"], default="csv")
    parser.add_argument("--cell")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--query", help="Parse a natural-language query using the configured LLM")
    parser.add_argument("--rag", action="store_true", help="Enable external embeddings and grounded LLM response")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--output", default="data/telecom_data/evaluation/rca_evaluation.json")
    parser.add_argument(
        "--simulate-action",
        action="store_true",
        help="Create a governed simulated corrective-action plan",
    )
    parser.add_argument(
        "--approve-action",
        action="store_true",
        help="Approve and execute the simulated action",
    )
    parser.add_argument(
        "--approved-by",
        help="Operator identity recorded when --approve-action is used",
    )
    parser.add_argument(
        "--audit-file",
        default="data/runtime/action_audit.jsonl",
        help="Append-only JSONL audit path for simulated actions",
    )
    parser.add_argument(
        "--force-verification-failure",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if args.approve_action and not args.simulate_action:
        parser.error("--approve-action requires --simulate-action")
    if args.approve_action and not args.approved_by:
        parser.error("--approved-by is required with --approve-action")
    rag = None
    if args.rag:
        from src.rag.rag_pipeline import TelecomRAGPipeline
        rag = TelecomRAGPipeline()
    graph = build_assurance_graph(EvidenceStore(args.backend), rag)
    if args.evaluate:
        scenarios = pd.read_csv("data/telecom_data/evaluation/scenario_truth.csv")
        results = []
        for scenario in scenarios.to_dict("records"):
            result = graph.invoke({k: scenario[k] for k in ("cell_id", "start_time", "end_time")})["result"]
            results.append({"scenario_id": scenario["scenario_id"], "expected": scenario["scenario_type"],
                            "predicted": result["likely_cause"], "confidence": result["confidence"],
                            "correct": result["likely_cause"] == scenario["scenario_type"],
                            "candidate_match": any(c["cause"] == scenario["scenario_type"] for c in result["candidates"])})
        report = {"total": len(results), "correct": sum(r["correct"] for r in results),
                  "candidate_matches": sum(r["candidate_match"] for r in results), "results": results}
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, indent=2))
        print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    else:
        if args.query:
            from src.query.query_understanding import understand_query
            filters = understand_query(args.query)
            state = {"cell_id": filters.cell_id, "start_time": filters.start_time, "end_time": filters.end_time}
        else:
            state = {"cell_id": args.cell, "start_time": args.start, "end_time": args.end}
        if not all(state.values()):
            parser.error("Provide a cell and bounded start/end times, or a query resolving all three")
        result = graph.invoke(state)["result"]
        if args.simulate_action:
            result["action_loop"] = run_action_loop(
                result,
                approved=args.approve_action,
                approved_by=args.approved_by,
                audit_path=args.audit_file,
                force_verification_failure=args.force_verification_failure,
            )
        print(json.dumps(result, default=str, indent=2))


if __name__ == "__main__":
    main()
