"""Safe, local corrective-action simulation with verification and audit events."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.analysis.incident import remediation_evidence_sufficient


ACTION_CATALOG = {
    "CONGESTION": {
        "action": "ADJUST_LOAD_BALANCING",
        "risk": "medium",
        "parameters": {"traffic_shift_pct": 20},
        "expected_outcome": "Downlink PRB utilization falls below 85%.",
    },
    "RADIO_INTERFERENCE": {
        "action": "APPLY_INTERFERENCE_MITIGATION",
        "risk": "medium",
        "parameters": {"sinr_improvement_db": 5, "rsrp_improvement_db": 3},
        "expected_outcome": "SINR or RSRP returns to the acceptable range.",
    },
    "TRANSPORT_DEGRADATION": {
        "action": "REROUTE_TRANSPORT_PATH",
        "risk": "medium",
        "parameters": {"alternate_path": "SIMULATED_STANDBY"},
        "expected_outcome": "Latency is at most 40 ms and packet loss at most 1%.",
    },
    "CELL_OUTAGE": {
        "action": "RESTART_CELL_SERVICE",
        "risk": "high",
        "parameters": {"restart_scope": "CELL"},
        "expected_outcome": "Cell availability returns to at least 99%.",
    },
    "CONFIGURATION_REGRESSION": {
        "action": "ROLLBACK_RECENT_CONFIGURATION",
        "risk": "high",
        "parameters": {"target": "MOST_RECENT_RELEVANT_CHANGE"},
        "expected_outcome": "Handover success is at least 93% and call drops at most 2%.",
    },
}


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _audit(audit_path, event):
    if audit_path is None:
        return
    path = Path(audit_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, default=str) + "\n")


def build_action_plan(rca_result):
    """Build a reversible simulated plan for the highest-ranked RCA candidate."""

    cause = rca_result.get("likely_cause")
    if cause not in ACTION_CATALOG:
        return None
    analysis = rca_result["analysis"]
    if not remediation_evidence_sufficient(cause, analysis):
        return None
    catalog = ACTION_CATALOG[cause]
    return {
        "action_id": str(uuid4()),
        "cell_id": analysis["cell_id"],
        "cause": cause,
        "action": catalog["action"],
        "parameters": deepcopy(catalog["parameters"]),
        "risk": catalog["risk"],
        "reversible": True,
        "approval_required": True,
        "expected_outcome": catalog["expected_outcome"],
        "original_metrics": deepcopy(analysis["metrics"]),
    }


def _project_metrics(cause, metrics):
    projected = deepcopy(metrics)
    if cause == "CONGESTION":
        projected["dl_prb_utilization"] = min(
            projected.get("dl_prb_utilization", 0) * 0.78, 82.0
        )
        projected["dl_throughput_mbps"] = projected.get(
            "dl_throughput_mbps", 0
        ) * 1.15
    elif cause == "RADIO_INTERFERENCE":
        projected["sinr_db"] = projected.get("sinr_db", 0) + 5
        projected["rsrp_dbm"] = projected.get("rsrp_dbm", -120) + 3
    elif cause == "TRANSPORT_DEGRADATION":
        projected["latency_ms"] = projected.get("latency_ms", 0) * 0.55
        projected["packet_loss_pct"] = projected.get("packet_loss_pct", 0) * 0.4
    elif cause == "CELL_OUTAGE":
        projected["availability_pct"] = 100.0
    elif cause == "CONFIGURATION_REGRESSION":
        projected["handover_success_rate"] = max(
            projected.get("handover_success_rate", 0), 97.0
        )
        projected["call_drop_rate"] = min(
            projected.get("call_drop_rate", 100), 1.0
        )
    return projected


def _verify(cause, metrics):
    checks = {
        "CONGESTION": metrics.get("dl_prb_utilization", 100) < 85,
        "RADIO_INTERFERENCE": (
            metrics.get("sinr_db", -100) >= 12
            or metrics.get("rsrp_dbm", -200) >= -95
        ),
        "TRANSPORT_DEGRADATION": (
            metrics.get("latency_ms", 1000) <= 40
            and metrics.get("packet_loss_pct", 100) <= 1
        ),
        "CELL_OUTAGE": metrics.get("availability_pct", 0) >= 99,
        "CONFIGURATION_REGRESSION": (
            metrics.get("handover_success_rate", 0) >= 93
            and metrics.get("call_drop_rate", 100) <= 2
        ),
    }
    return bool(checks[cause])


def run_action_loop(
    rca_result,
    approved=False,
    approved_by=None,
    audit_path="data/runtime/action_audit.jsonl",
    force_verification_failure=False,
    plan=None,
):
    """Plan, approve, simulate, verify, and roll back a corrective action."""

    existing_plan = plan is not None
    plan = plan or build_action_plan(rca_result)
    if plan is None:
        return {
            "status": "no_action_available",
            "reason": "No supported RCA candidate with sufficient remediation evidence was available.",
        }

    events = []

    def record(event_type, **details):
        event = {
            "timestamp": _timestamp(),
            "action_id": plan["action_id"],
            "cell_id": plan["cell_id"],
            "event": event_type,
            **details,
        }
        events.append(event)
        _audit(audit_path, event)

    if not existing_plan:
        record("ACTION_PLANNED", cause=plan["cause"], action=plan["action"])
    if not approved:
        record("APPROVAL_REQUIRED", risk=plan["risk"])
        return {
            "status": "awaiting_approval",
            "plan": plan,
            "audit_events": events,
        }

    if not approved_by:
        raise ValueError("approved_by is required when approved=True")

    record("ACTION_APPROVED", approved_by=approved_by)
    projected = _project_metrics(plan["cause"], plan["original_metrics"])
    if force_verification_failure:
        projected = deepcopy(plan["original_metrics"])
    record("ACTION_SIMULATED", projected_metrics=projected)

    verification_passed = _verify(plan["cause"], projected)
    record("VERIFICATION_COMPLETED", passed=verification_passed)
    if verification_passed:
        return {
            "status": "completed",
            "plan": plan,
            "projected_metrics": projected,
            "verification_passed": True,
            "audit_events": events,
        }

    record("ACTION_ROLLED_BACK", restored_metrics=plan["original_metrics"])
    return {
        "status": "rolled_back",
        "plan": plan,
        "projected_metrics": projected,
        "restored_metrics": plan["original_metrics"],
        "verification_passed": False,
        "audit_events": events,
    }
