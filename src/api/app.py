"""FastAPI surface for incident analysis and governed simulated actions."""

import json
import logging
import os
import secrets
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.actions import run_action_loop
from src.analysis.incident import EvidenceStore
from src.services.incident_store import IncidentStore
from src.services.observability import CorrelationMiddleware, Observability, identifiers, observe
from src.workflows.assurance import build_assurance_graph


class AnalyzeRequest(BaseModel):
    cell_id: str = Field(min_length=1, max_length=50)
    start_time: str
    end_time: str
    backend: Literal["csv", "postgres"] = "csv"
    rag: bool = False


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    incident_id: str | None = None
    backend: Literal["csv", "postgres"] = "csv"
    rag: bool = False


class ApprovalRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=200)


def _json_safe(value):
    return json.loads(json.dumps(value, default=str))


def _format_chat_answer(result):
    analysis = result["analysis"]
    cell_id = analysis["cell_id"]
    start = analysis["start_time"].replace("T", " ")
    end = analysis["end_time"].replace("T", " ")

    if result["status"] == "insufficient_evidence":
        return (
            f"I could not find KPI samples for {cell_id} between {start} and {end}. "
            "Check the cell ID and use a time window covered by the August 2026 dataset."
        )
    if not result["candidates"]:
        return (
            f"I analyzed {cell_id} between {start} and {end}. The available KPIs did "
            "not cross any configured incident threshold."
        )

    primary = result["candidates"][0]
    evidence = "; ".join(primary["evidence"])
    answer = (
        f"The most likely cause for {cell_id} between {start} and {end} is "
        f"{primary['cause'].replace('_', ' ').title()} "
        f"(confidence share {result['confidence']:.0%}).\n\n"
        f"Evidence: {evidence}.\n\n"
        f"Recommended next step: {primary['recommendation']}"
    )
    alternatives = result["candidates"][1:]
    if alternatives:
        answer += "\n\nOther signals also support: " + ", ".join(
            candidate["cause"].replace("_", " ").title()
            for candidate in alternatives
        ) + "."

    knowledge = result.get("knowledge_answer", {}).get("answer", {})
    if knowledge:
        answer += f"\n\nKnowledge-base guidance: {knowledge.get('summary', '')}"
        investigation = knowledge.get("recommended_investigation", [])
        if investigation:
            answer += "\n" + "\n".join(f"• {item}" for item in investigation)
    return answer


def create_app(
    data_dir="data/telecom_data",
    database_path=None,
    audit_path=None,
    api_key=None,
    query_understander=None,
):
    app = FastAPI(
        title="Enterprise Service Assurance & Resolution Platform",
        version="0.2.0",
        description="Telecom incident analysis, RCA, and corrective-action simulation.",
    )
    app.state.incidents = IncidentStore(
        database_path or os.getenv("INCIDENT_DB_PATH", "data/runtime/incidents.db")
    )
    app.state.audit_path = audit_path or os.getenv(
        "ACTION_AUDIT_PATH", "data/runtime/action_audit.jsonl"
    )
    app.state.api_key = api_key or os.getenv("SERVICE_API_KEY", "development-only")
    app.state.graphs = {}
    app.state.telemetry = Observability()
    app.add_middleware(CorrelationMiddleware, telemetry=app.state.telemetry)

    def require_api_key(x_api_key: str = Header(default="")):
        if not secrets.compare_digest(x_api_key, app.state.api_key):
            raise HTTPException(status_code=401, detail="Invalid API key")

    def get_graph(backend, rag):
        cache_key = (backend, rag)
        if cache_key not in app.state.graphs:
            rag_pipeline = None
            if rag:
                from src.rag.rag_pipeline import TelecomRAGPipeline

                rag_pipeline = TelecomRAGPipeline()
            app.state.graphs[cache_key] = build_assurance_graph(
                EvidenceStore(backend=backend, data_dir=data_dir),
                rag_pipeline,
            )
        return app.state.graphs[cache_key]

    def run_analysis(backend, rag, payload, incident_id):
        started = perf_counter()
        identifiers.set({"incident_id": incident_id})
        try:
            result = get_graph(backend, rag).invoke(payload)["result"]
        except Exception:
            observe("incident.analysis", "failed", started, severity=logging.ERROR)
            raise
        observe("incident.analysis", result["status"], started,
                cause=result.get("likely_cause"))
        return result

    @app.get("/metrics", dependencies=[Depends(require_api_key)], include_in_schema=False)
    def metrics():
        try:
            if app.state.telemetry.registry is None:
                raise RuntimeError("Metrics unavailable")
            return Response(generate_latest(app.state.telemetry.registry),
                            headers={"Content-Type": CONTENT_TYPE_LATEST})
        except Exception:
            observe("metrics.export", "failed", severity=logging.ERROR)
            raise HTTPException(status_code=503, detail="Metrics temporarily unavailable") from None

    def understand(message):
        parser = query_understander
        if parser is None:
            from src.query.query_understanding import understand_query

            parser = understand_query
        parsed = parser(message)
        return parsed.model_dump() if hasattr(parsed, "model_dump") else dict(parsed)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": app.version}

    @app.get("/health/ready")
    def readiness():
        try:
            app.state.incidents.check_health()
            for name in ("cell_kpi", "alarms", "configuration_changes", "tickets"):
                with (Path(data_dir) / f"{name}.csv").open("rb") as stream:
                    if not stream.read(1):
                        raise OSError("Empty evidence file")
        except Exception:
            raise HTTPException(status_code=503, detail="Service not ready") from None
        return {"status": "ready"}

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.post("/api/incidents", dependencies=[Depends(require_api_key)])
    def analyze_incident(request: AnalyzeRequest):
        payload = request.model_dump()
        incident_id = str(uuid4())
        try:
            result = run_analysis(
                request.backend, request.rag,
                {
                    "cell_id": request.cell_id,
                    "start_time": request.start_time,
                    "end_time": request.end_time,
                }, incident_id
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        result = _json_safe(result)
        app.state.incidents.save_incident(incident_id, payload, result)
        return {"incident_id": incident_id, "result": result}

    @app.post("/api/chat", dependencies=[Depends(require_api_key)])
    def chat(request: ChatRequest):
        previous = None
        if request.incident_id:
            previous = app.state.incidents.get_incident(request.incident_id)
            if previous is None:
                raise HTTPException(status_code=404, detail="Conversation incident not found")

        try:
            filters = understand(request.message)
        except Exception as error:
            raise HTTPException(
                status_code=502,
                detail=f"Could not understand the question: {error}",
            ) from error

        if previous:
            filters["cell_id"] = filters.get("cell_id") or previous["cell_id"]
            filters["start_time"] = filters.get("start_time") or previous["start_time"]
            filters["end_time"] = filters.get("end_time") or previous["end_time"]

        missing = [
            field
            for field in ("cell_id", "start_time", "end_time")
            if not filters.get(field)
        ]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Please include a cell ID and a bounded time window. "
                    "For example: What happened to CELL_028_1 between "
                    "2026-08-05 07:00:00 and 2026-08-05 10:00:00?"
                ),
            )

        incident_id = str(uuid4())
        try:
            result = run_analysis(
                request.backend, request.rag,
                {
                    "cell_id": filters["cell_id"],
                    "start_time": filters["start_time"],
                    "end_time": filters["end_time"],
                }, incident_id
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        result = _json_safe(result)
        app.state.incidents.save_incident(
            incident_id,
            {
                "cell_id": filters["cell_id"],
                "start_time": filters["start_time"],
                "end_time": filters["end_time"],
            },
            result,
        )
        return {
            "incident_id": incident_id,
            "answer": _format_chat_answer(result),
            "filters": {
                field: filters.get(field)
                for field in ("cell_id", "site_id", "start_time", "end_time")
            },
            "result": result,
        }

    @app.get(
        "/api/incidents/{incident_id}",
        dependencies=[Depends(require_api_key)],
    )
    def get_incident(incident_id: str):
        incident = app.state.incidents.get_incident(incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        incident["actions"] = app.state.incidents.list_actions(incident_id)
        return incident

    @app.post(
        "/api/incidents/{incident_id}/actions",
        dependencies=[Depends(require_api_key)],
    )
    def plan_action(incident_id: str):
        started = perf_counter()
        identifiers.set({"incident_id": incident_id})
        try:
            incident = app.state.incidents.get_incident(incident_id)
            if incident is None:
                raise HTTPException(status_code=404, detail="Incident not found")
            action_result = run_action_loop(
                incident["result"],
                audit_path=app.state.audit_path,
            )
            if action_result["status"] == "no_action_available":
                observe("action.planning", "rejected", started)
                raise HTTPException(status_code=409, detail=action_result["reason"])
            action_result = _json_safe(action_result)
            app.state.incidents.save_action_plan(incident_id, action_result)
            observe("action.planning", "awaiting_approval", started,
                    action_id=action_result["plan"]["action_id"])
            return action_result
        except HTTPException:
            raise
        except Exception:
            observe("action.planning", "failed", started, severity=logging.ERROR)
            raise

    @app.post(
        "/api/actions/{action_id}/approve",
        dependencies=[Depends(require_api_key)],
    )
    def approve_action(action_id: str, request: ApprovalRequest):
        started = perf_counter()
        identifiers.set({"action_id": action_id})
        action = app.state.incidents.get_action(action_id)
        if action is None:
            raise HTTPException(status_code=404, detail="Action plan not found")
        identifiers.set({"action_id": action_id, "incident_id": action["incident_id"]})
        try:
            claimed = app.state.incidents.claim_action(action_id, request.approved_by)
        except Exception:
            observe("action.claim", "failed", started, severity=logging.ERROR)
            raise
        if not claimed:
            # Re-read after the conditional update: another request may have
            # completed while this request was waiting for SQLite's write lock.
            action = app.state.incidents.get_action(action_id)
            if action["status"] in {"completed", "rolled_back"}:
                observe("action.claim", "replayed", started)
                return action["result"]
            observe("action.claim", "rejected", started)
            observe("approval.conflict", action["status"], started)
            if action["status"] == "executing":
                raise HTTPException(status_code=409, detail="Action is already executing")
            raise HTTPException(status_code=409, detail="Action is not awaiting approval")

        observe("action.claim", "claimed", started)
        execution_started = perf_counter()
        try:
            incident = app.state.incidents.get_incident(action["incident_id"])
            result = run_action_loop(
                incident["result"],
                approved=True,
                approved_by=request.approved_by,
                audit_path=app.state.audit_path,
                plan=action["plan"],
            )
            result = _json_safe(result)
            app.state.incidents.complete_action(
                action_id,
                request.approved_by,
                result,
            )
        except Exception:
            observe("action.execution", "failed", execution_started, severity=logging.ERROR)
            app.state.incidents.complete_action(
                action_id,
                request.approved_by,
                {
                    "status": "failed",
                    "plan": action["plan"],
                    "reason": "Unexpected action execution failure; manual recovery required.",
                },
            )
            raise HTTPException(status_code=500, detail="Action execution failed") from None
        observe("action.execution", result["status"], execution_started)
        return result

    return app


app = create_app()
