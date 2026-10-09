"""Operational evidence collection, analysis, and deterministic RCA scoring."""

from datetime import datetime, timedelta
from pathlib import Path
from math import isfinite
from operator import ge, gt, lt

import pandas as pd


METRICS = [
    "dl_prb_utilization",
    "call_drop_rate",
    "handover_success_rate",
    "dl_throughput_mbps",
    "availability_pct",
    "latency_ms",
    "packet_loss_pct",
    "rsrp_dbm",
    "sinr_db",
]

CAUSES = [
    "CELL_OUTAGE",
    "TRANSPORT_DEGRADATION",
    "CONGESTION",
    "RADIO_INTERFERENCE",
    "CONFIGURATION_REGRESSION",
]

ALARM_CAUSE_MAP = {
    "CELL_UNAVAILABLE": "CELL_OUTAGE",
    "TRANSPORT_PACKET_LOSS": "TRANSPORT_DEGRADATION",
    "TRANSPORT_LINK_FLAP": "TRANSPORT_DEGRADATION",
    "HIGH_RESOURCE_UTILIZATION": "CONGESTION",
    "RADIO_QUALITY_DEGRADATION": "RADIO_INTERFERENCE",
    "MINOR_VSWR_WARNING": "RADIO_INTERFERENCE",
    "HANDOVER_FAILURE_RATE_HIGH": "CONFIGURATION_REGRESSION",
}

PRIMARY_ALARMS = {
    "CELL_UNAVAILABLE",
    "TRANSPORT_PACKET_LOSS",
    "HIGH_RESOURCE_UTILIZATION",
    "RADIO_QUALITY_DEGRADATION",
    "HANDOVER_FAILURE_RATE_HIGH",
}

TICKET_KEYWORDS = {
    "CELL_OUTAGE": ("complete service loss", "connectivity issue"),
    "TRANSPORT_DEGRADATION": ("latency", "packet loss"),
    "CONGESTION": ("slow data", "low throughput", "peak hours"),
    "RADIO_INTERFERENCE": ("poor radio quality", "voice quality"),
    "CONFIGURATION_REGRESSION": ("mobility", "recent network activity", "call drops"),
}

CONFIGURATION_PARAMETERS = {
    "handover_margin_db",
    "qrxlevmin_dbm",
    "tx_power_dbm",
    "antenna_tilt_deg",
    "cell_reselection_offset_db",
    "max_connected_users",
}

RECOMMENDATIONS = {
    "CELL_OUTAGE": "Investigate power, transport connectivity and cell administrative state.",
    "TRANSPORT_DEGRADATION": "Inspect backhaul latency, packet loss and transport alarms.",
    "CONGESTION": "Review traffic demand, capacity and load-balancing options.",
    "RADIO_INTERFERENCE": "Inspect spectrum interference, radio quality and antenna alarms.",
    "CONFIGURATION_REGRESSION": "Compare recent parameter changes with the approved configuration; assess rollback.",
}


# Shared diagnostic thresholds: planning counts distinct measurements, not score share.
KPI_RULES = (
    ("CELL_OUTAGE", "availability_pct", lt, 50, "Mean availability below 50%", 5.0),
    ("TRANSPORT_DEGRADATION", "latency_ms", gt, 40, "Mean latency above 40 ms", 1.5),
    ("TRANSPORT_DEGRADATION", "packet_loss_pct", gt, 1, "Mean packet loss above 1%", 2.5),
    ("CONGESTION", "dl_prb_utilization", gt, 85, "Mean downlink PRB utilization above 85%", 3.0),
    ("RADIO_INTERFERENCE", "sinr_db", lt, 12, "Mean SINR below 12 dB", 2.5),
    ("RADIO_INTERFERENCE", "rsrp_dbm", lt, -95, "Mean RSRP below -95 dBm", 2.0),
    ("CONFIGURATION_REGRESSION", "handover_success_rate", lt, 93, "Mean handover success below 93%", 2.5),
    ("CONFIGURATION_REGRESSION", "call_drop_rate", gt, 2, "Mean call drop rate above 2%", 1.0),
)


def _breached(metrics, metric, compare, threshold):
    value = metrics.get(metric)
    return isinstance(value, (int, float)) and isfinite(value) and compare(value, threshold)


def remediation_evidence_sufficient(cause, analysis):
    """Conservative planning policy, independent of normalized heuristic confidence.

    Require two cause-specific KPI breaches, or one plus mapped alarm, matching
    ticket text, or (for configuration regression only) a preceding relevant change.
    Standalone severe availability loss (<50%) and near-saturated PRB (>=95%,
    at most 5% headroom) remain eligible. Missing/nonfinite metrics never count.
    Legacy hand-built RCA fixtures use the same raw-evidence policy; their omitted
    event collections count as empty, with no exemption for missing candidates.
    This permits investigation-only results for severe single transport/radio KPIs.
    """
    metrics = analysis.get("metrics", {})
    if cause == "CELL_OUTAGE" and _breached(metrics, "availability_pct", lt, 50):
        return True
    if cause == "CONGESTION" and _breached(metrics, "dl_prb_utilization", ge, 95):
        return True
    breaches = sum(
        _breached(metrics, metric, compare, threshold)
        for rule_cause, metric, compare, threshold, _, _ in KPI_RULES
        if rule_cause == cause
    )
    if breaches >= 2:
        return True
    if not breaches:
        return False
    matching_alarm = any(
        ALARM_CAUSE_MAP.get(signal.get("alarm_name")) == cause
        and signal.get("cause") == cause
        for signal in analysis.get("alarm_signals", [])
    )
    matching_ticket = any(
        keyword in str(ticket.get("issue_summary", "")).lower()
        for ticket in analysis.get("tickets", [])
        for keyword in TICKET_KEYWORDS.get(cause, ())
    )
    matching_change = cause == "CONFIGURATION_REGRESSION" and bool(
        analysis.get("preceding_relevant_changes", [])
    )
    return matching_alarm or matching_ticket or matching_change


class EvidenceStore:
    """Read incident evidence from bundled CSV files or PostgreSQL."""

    def __init__(self, backend="csv", data_dir="data/telecom_data"):
        if backend not in {"csv", "postgres"}:
            raise ValueError("backend must be csv or postgres")
        self.backend = backend
        self.frames = {}
        if backend == "csv":
            for table, time_column in [
                ("cell_kpi", "timestamp"),
                ("alarms", "timestamp"),
                ("configuration_changes", "timestamp"),
                ("tickets", "created_time"),
            ]:
                frame = pd.read_csv(
                    Path(data_dir) / f"{table}.csv",
                    parse_dates=[time_column],
                )
                if table == "alarms":
                    frame["clear_time"] = pd.to_datetime(frame["clear_time"])
                self.frames[table] = frame

    def read(self, table, cell, start, end):
        time_column = "created_time" if table == "tickets" else "timestamp"
        if table not in {
            "cell_kpi",
            "alarms",
            "configuration_changes",
            "tickets",
        }:
            raise ValueError("Unknown evidence table")

        if self.backend == "postgres":
            from src.database.postgres import execute_query

            if table == "alarms":
                clause = "timestamp < %s AND (clear_time IS NULL OR clear_time >= %s)"
                params = (cell, end, start)
            else:
                clause = f"{time_column} >= %s AND {time_column} < %s"
                params = (cell, start, end)
            return pd.DataFrame(
                execute_query(
                    f"SELECT * FROM {table} WHERE cell_id = %s AND {clause} "
                    f"ORDER BY {time_column}",
                    params,
                )
            )

        frame = self.frames[table]
        if table == "alarms":
            mask = (frame[time_column] < end) & (
                frame.clear_time.isna() | (frame.clear_time >= start)
            )
        else:
            mask = (frame[time_column] >= start) & (frame[time_column] < end)
        return frame[(frame.cell_id == cell) & mask].copy()


def collect_evidence(store, cell_id, start_time, end_time):
    """Collect the incident, baseline, and surrounding event windows."""

    start = datetime.fromisoformat(str(start_time))
    end = datetime.fromisoformat(str(end_time))
    if not cell_id or start >= end:
        raise ValueError("A cell ID and an increasing time window are required")

    return {
        "cell_id": cell_id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "kpis": store.read("cell_kpi", cell_id, start, end),
        "baseline": store.read(
            "cell_kpi", cell_id, start - timedelta(hours=2), start
        ),
        "alarms": store.read("alarms", cell_id, start, end),
        "changes": store.read(
            "configuration_changes", cell_id, start - timedelta(hours=2), end
        ),
        "tickets": store.read(
            "tickets", cell_id, start, end + timedelta(hours=2)
        ),
    }


def _records(frame):
    return frame.astype(object).where(pd.notna(frame), None).to_dict("records")


def analyze_kpis(evidence):
    """KPI-agent contract: summarize incident and pre-incident measurements."""

    def means(frame):
        return {
            metric: float(frame[metric].mean())
            for metric in METRICS
            if metric in frame and frame[metric].notna().any()
        }

    current = means(evidence["kpis"])
    baseline = means(evidence["baseline"])
    return {
        "sample_count": len(evidence["kpis"]),
        "baseline_sample_count": len(evidence["baseline"]),
        "metrics": current,
        "baseline_metrics": baseline,
        "deltas": {
            metric: current[metric] - baseline[metric]
            for metric in current.keys() & baseline.keys()
        },
    }


def analyze_alarms(evidence):
    """Alarm-agent contract: normalize alarms and expose mapped RCA signals."""

    alarms = _records(evidence["alarms"])
    signals = [
        {
            "alarm_id": alarm["alarm_id"],
            "alarm_name": alarm["alarm_name"],
            "cause": ALARM_CAUSE_MAP[alarm["alarm_name"]],
            "timestamp": alarm["timestamp"],
            "primary": alarm["alarm_name"] in PRIMARY_ALARMS,
        }
        for alarm in alarms
        if alarm.get("alarm_name") in ALARM_CAUSE_MAP
    ]
    return {"alarms": alarms, "alarm_signals": signals}


def analyze_changes(evidence):
    """Configuration-agent contract: identify changes preceding incident onset."""

    start = pd.Timestamp(evidence["start_time"])
    changes = _records(evidence["changes"])
    preceding = [
        change
        for change in changes
        if pd.Timestamp(change["timestamp"]) <= start
        and change.get("parameter_name") in CONFIGURATION_PARAMETERS
    ]
    return {
        "changes": changes,
        "preceding_relevant_changes": preceding,
    }


def analyze_tickets(evidence):
    """Ticket-agent contract: normalize tickets for text-based supporting signals."""

    return {"tickets": _records(evidence["tickets"])}


def assemble_analysis(evidence, kpi, alarms, changes, tickets):
    """Combine specialized agent outputs into the RCA input contract."""

    timeline = []
    for kind, items, time_key, id_key in [
        ("alarm", alarms["alarms"], "timestamp", "alarm_id"),
        ("configuration_change", changes["changes"], "timestamp", "change_id"),
        ("ticket", tickets["tickets"], "created_time", "ticket_id"),
    ]:
        timeline.extend(
            {
                "kind": kind,
                "id": item[id_key],
                "timestamp": str(item[time_key]),
            }
            for item in items
        )
    timeline.sort(key=lambda event: pd.Timestamp(event["timestamp"]))

    return {
        "cell_id": evidence["cell_id"],
        "start_time": evidence["start_time"],
        "end_time": evidence["end_time"],
        **kpi,
        **alarms,
        **changes,
        **tickets,
        "timeline": timeline,
        "event_counts": {
            "alarms": len(alarms["alarms"]),
            "configuration_changes": len(changes["changes"]),
            "tickets": len(tickets["tickets"]),
        },
    }


def analyze_evidence(evidence):
    """Backward-compatible single-call analysis wrapper."""

    return assemble_analysis(
        evidence,
        analyze_kpis(evidence),
        analyze_alarms(evidence),
        analyze_changes(evidence),
        analyze_tickets(evidence),
    )


def _alarm_alignment_score(signal, start, end):
    """Favor an alarm whose onset aligns with the requested incident boundary."""

    duration = max((end - start).total_seconds(), 1)
    distance = abs((pd.Timestamp(signal["timestamp"]) - start).total_seconds())
    alignment = max(0.2, 1.0 - distance / duration)
    return (6.0 if signal["primary"] else 1.0) * alignment


def diagnose(analysis):
    """Rank explainable RCA hypotheses using KPI, alarm, change, and ticket evidence."""

    metrics = analysis.get("metrics", {})
    if not metrics:
        return {
            "status": "insufficient_evidence",
            "likely_cause": None,
            "confidence": 0.0,
            "candidates": [],
            "analysis": analysis,
            "limitations": ["No KPI samples were available for the requested window."],
        }

    evidence_by_cause = {cause: [] for cause in CAUSES}
    score_by_cause = {cause: 0.0 for cause in CAUSES}
    qualifying_causes = set()

    def add_kpi(cause, condition, reason, weight):
        if condition:
            qualifying_causes.add(cause)
            score_by_cause[cause] += weight
            evidence_by_cause[cause].append(reason)

    for cause, metric, compare, threshold, reason, weight in KPI_RULES:
        add_kpi(cause, _breached(metrics, metric, compare, threshold), reason, weight)

    start = pd.Timestamp(analysis["start_time"])
    end = pd.Timestamp(analysis.get("end_time", start + pd.Timedelta(hours=1)))
    for signal in analysis.get("alarm_signals", []):
        cause = signal["cause"]
        if signal["primary"]:
            qualifying_causes.add(cause)
        score_by_cause[cause] += _alarm_alignment_score(signal, start, end)
        evidence_by_cause[cause].append(
            f"Alarm {signal['alarm_name']} ({signal['alarm_id']}) overlapped the incident"
        )

    preceding_changes = analysis.get("preceding_relevant_changes", [])
    if preceding_changes:
        score_by_cause["CONFIGURATION_REGRESSION"] += min(
            2.0, 0.75 * len(preceding_changes)
        )
        evidence_by_cause["CONFIGURATION_REGRESSION"].append(
            f"{len(preceding_changes)} relevant configuration change(s) preceded incident onset"
        )

    ticket_text = " ".join(
        str(ticket.get("issue_summary", "")).lower()
        for ticket in analysis.get("tickets", [])
    )
    for cause, keywords in TICKET_KEYWORDS.items():
        matches = [keyword for keyword in keywords if keyword in ticket_text]
        if matches:
            score_by_cause[cause] += min(1.0, 0.5 * len(matches))
            evidence_by_cause[cause].append(
                "Ticket text matched: " + ", ".join(matches)
            )

    candidates = []
    for cause in qualifying_causes:
        supporting_change_ids = (
            [change["change_id"] for change in preceding_changes]
            if cause == "CONFIGURATION_REGRESSION"
            else []
        )
        candidates.append(
            {
                "cause": cause,
                "score": round(score_by_cause[cause], 3),
                "evidence": evidence_by_cause[cause],
                "recommendation": RECOMMENDATIONS[cause],
                "supporting_change_ids": supporting_change_ids,
            }
        )

    cause_order = {cause: index for index, cause in enumerate(CAUSES)}
    candidates.sort(
        key=lambda candidate: (
            -candidate["score"],
            cause_order[candidate["cause"]],
        )
    )

    total_score = sum(candidate["score"] for candidate in candidates)
    confidence = candidates[0]["score"] / total_score if candidates else 0.0
    return {
        "status": "investigation_required" if candidates else "no_threshold_breach",
        "likely_cause": candidates[0]["cause"] if candidates else None,
        "confidence": round(confidence, 3),
        "candidates": candidates,
        "analysis": analysis,
        "limitations": [
            "Scores rank investigation hypotheses; they do not confirm root cause.",
            "The two-hour baseline may contain another incident or a different traffic pattern.",
        ],
    }
