"""Conditional LangGraph orchestration for telecom assurance agents."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from src.analysis.incident import (
    analyze_alarms,
    analyze_changes,
    analyze_kpis,
    analyze_tickets,
    assemble_analysis,
    collect_evidence,
    diagnose,
)


class AssuranceState(TypedDict, total=False):
    cell_id: str
    start_time: str
    end_time: str
    evidence: dict
    selected_agents: list[str]
    completed_agents: list[str]
    kpi_findings: dict
    alarm_findings: dict
    change_findings: dict
    ticket_findings: dict
    analysis: dict
    result: dict


AGENT_TO_NODE = {
    "kpi": "kpi_agent",
    "alarm": "alarm_agent",
    "configuration": "configuration_agent",
    "ticket": "ticket_agent",
}


def _select_agents(evidence):
    selected = []
    for agent, key in [
        ("kpi", "kpis"),
        ("alarm", "alarms"),
        ("configuration", "changes"),
        ("ticket", "tickets"),
    ]:
        if not evidence[key].empty:
            selected.append(agent)
    return selected


def build_assurance_graph(store, rag_pipeline=None):
    """Build a supervisor graph that invokes only agents with available evidence."""

    graph = StateGraph(AssuranceState)

    def collect(state):
        return {
            "evidence": collect_evidence(
                store,
                state["cell_id"],
                state["start_time"],
                state["end_time"],
            )
        }

    def supervisor(state):
        return {
            "selected_agents": _select_agents(state["evidence"]),
            "completed_agents": [],
        }

    def next_agent(state):
        completed = set(state.get("completed_agents", []))
        for agent in state.get("selected_agents", []):
            if agent not in completed:
                return AGENT_TO_NODE[agent]
        return "assemble"

    def mark_complete(state, agent, output_key, output):
        return {
            output_key: output,
            "completed_agents": [*state.get("completed_agents", []), agent],
        }

    def assemble(state):
        empty_kpi = {
            "sample_count": 0,
            "baseline_sample_count": 0,
            "metrics": {},
            "baseline_metrics": {},
            "deltas": {},
        }
        return {
            "analysis": assemble_analysis(
                state["evidence"],
                state.get("kpi_findings", empty_kpi),
                state.get("alarm_findings", {"alarms": [], "alarm_signals": []}),
                state.get(
                    "change_findings",
                    {"changes": [], "preceding_relevant_changes": []},
                ),
                state.get("ticket_findings", {"tickets": []}),
            )
        }

    def rca(state):
        result = diagnose(state["analysis"])
        result["orchestration"] = {
            "selected_agents": state.get("selected_agents", []),
            "completed_agents": state.get("completed_agents", []),
        }
        if rag_pipeline is not None and result["candidates"]:
            result["knowledge_answer"] = rag_pipeline.ask_incident(result)
        return {"result": result}

    graph.add_node("collect", collect)
    graph.add_node("supervisor", supervisor)
    graph.add_node("dispatch", lambda state: {})
    graph.add_node(
        "kpi_agent",
        lambda state: mark_complete(
            state, "kpi", "kpi_findings", analyze_kpis(state["evidence"])
        ),
    )
    graph.add_node(
        "alarm_agent",
        lambda state: mark_complete(
            state,
            "alarm",
            "alarm_findings",
            analyze_alarms(state["evidence"]),
        ),
    )
    graph.add_node(
        "configuration_agent",
        lambda state: mark_complete(
            state,
            "configuration",
            "change_findings",
            analyze_changes(state["evidence"]),
        ),
    )
    graph.add_node(
        "ticket_agent",
        lambda state: mark_complete(
            state,
            "ticket",
            "ticket_findings",
            analyze_tickets(state["evidence"]),
        ),
    )
    graph.add_node("assemble", assemble)
    graph.add_node("rca", rca)

    graph.add_edge(START, "collect")
    graph.add_edge("collect", "supervisor")
    graph.add_edge("supervisor", "dispatch")
    graph.add_conditional_edges(
        "dispatch",
        next_agent,
        {
            "kpi_agent": "kpi_agent",
            "alarm_agent": "alarm_agent",
            "configuration_agent": "configuration_agent",
            "ticket_agent": "ticket_agent",
            "assemble": "assemble",
        },
    )
    for node in AGENT_TO_NODE.values():
        graph.add_edge(node, "dispatch")
    graph.add_edge("assemble", "rca")
    graph.add_edge("rca", END)
    return graph.compile()
