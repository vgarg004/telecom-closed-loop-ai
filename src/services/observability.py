"""Best-effort structured telemetry; no evidence, credentials, or exception text."""

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter
from uuid import UUID, uuid4

from prometheus_client import CollectorRegistry, Counter, Histogram
from starlette.responses import PlainTextResponse

request_id = ContextVar("request_id", default=None)
observer = ContextVar("observer", default=None)
identifiers = ContextVar("identifiers", default={})

ROUTES = frozenset({"/", "/health", "/metrics", "/docs", "/docs/oauth2-redirect",
                    "/redoc", "/openapi.json", "/api/incidents", "/api/chat",
                    "/api/incidents/{incident_id}", "/api/incidents/{incident_id}/actions",
                    "/api/actions/{action_id}/approve"})
CAUSES = frozenset({"CELL_OUTAGE", "TRANSPORT_DEGRADATION", "CONGESTION",
                    "RADIO_INTERFERENCE", "CONFIGURATION_REGRESSION"})
OUTCOMES = frozenset({"investigation_required", "no_threshold_breach", "insufficient_evidence",
                      "awaiting_approval", "completed", "rolled_back", "failed", "rejected",
                      "claimed", "replayed", "executing", "passed", "simulated", "success"})
STAGES = frozenset({"planning", "claim", "execution", "simulation", "verification", "rollback"})


def bounded(value, choices):
    return value if value in choices else "other"


def valid_request_id(value):
    """Only canonical UUIDs are accepted; arbitrary header text is never logged."""
    try:
        if value and str(UUID(value)) == value.lower():
            return value
    except (ValueError, AttributeError):
        pass
    return str(uuid4())


class JsonFormatter(logging.Formatter):
    def format(self, record):
        # Deliberately ignore message, args, exc_info and all non-allowlisted extras.
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "severity": record.levelname,
            "event": getattr(record, "event", "application"),
            "correlation_id": getattr(record, "correlation_id", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "outcome": getattr(record, "outcome", "other"),
        }
        for key in ("incident_id", "action_id", "route", "method", "status_code", "cause"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload)


logger = logging.getLogger("telecom.observability")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def observe(event, outcome, started=None, severity=logging.INFO, **fields):
    """Telemetry failures never change execution or persistence behavior."""
    outcome = bounded(outcome, OUTCOMES)
    safe = {key: value for key, value in fields.items()
            if key in {"incident_id", "action_id", "route", "method", "status_code", "cause"}}
    safe = {**identifiers.get(), **safe}
    # URL identifiers are untrusted too; only generated UUID identities are logged.
    for key in ("incident_id", "action_id"):
        if key in safe:
            try:
                safe[key] = str(UUID(str(safe[key])))
            except (ValueError, AttributeError):
                safe[key] = "invalid-id"
    if "cause" in safe:
        safe["cause"] = bounded(safe["cause"], CAUSES)
    try:
        logger.log(severity, event, extra={
            **safe, "event": event, "outcome": outcome,
            "correlation_id": request_id.get(),
            "duration_ms": (perf_counter() - started) * 1000 if started is not None else None,
        })
    except Exception:
        pass
    try:
        current = observer.get()
        if current is not None:
            current.record(event, outcome, safe.get("cause"))
    except Exception:
        pass


class Observability:
    def __init__(self):
        self.registry = None
        try:
            self.registry = CollectorRegistry()
            self.requests = Counter("telecom_http_requests_total", "HTTP responses by route and status class",
                                    ("method", "route", "status_class"), registry=self.registry)
            self.errors = Counter("telecom_http_errors_total", "HTTP 4xx and 5xx responses",
                                  ("method", "route", "status_class"), registry=self.registry)
            self.duration = Histogram("telecom_http_request_duration_seconds", "End-to-end HTTP duration",
                                      ("method", "route"), registry=self.registry,
                                      buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10))
            self.rca = Counter("telecom_rca_outcomes_total", "Fresh RCA computations, including abstention",
                               ("outcome", "cause"), registry=self.registry)
            self.actions = Counter("telecom_action_outcomes_total", "Action lifecycle events by stage",
                                   ("stage", "outcome"), registry=self.registry)
            self.conflicts = Counter("telecom_approval_conflicts_total", "Rejected approval claims",
                                     ("reason",), registry=self.registry)
        except Exception:
            # A degraded telemetry subsystem must not prevent app startup.
            self.registry = None

    def record(self, event, outcome, cause=None):
        if event == "incident.analysis":
            self.rca.labels(bounded(outcome, OUTCOMES), bounded(cause, CAUSES)).inc()
        elif event.startswith("action."):
            stage = event.split(".", 1)[1]
            if stage in STAGES:
                self.actions.labels(stage, bounded(outcome, OUTCOMES)).inc()
        if event == "approval.conflict":
            self.conflicts.labels(bounded(outcome, {"executing", "failed", "rejected"})).inc()

    def request(self, method, route, status, duration):
        try:
            method = bounded(method, {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
            route = bounded(route, ROUTES)
            status_class = f"{status // 100}xx" if 100 <= status < 600 else "other"
            self.requests.labels(method, route, status_class).inc()
            self.duration.labels(method, route).observe(duration)
            if status >= 400:
                self.errors.labels(method, route, status_class).inc()
        except Exception:
            pass


class CorrelationMiddleware:
    """Pure ASGI middleware preserves context in FastAPI's worker threads."""
    def __init__(self, app, telemetry):
        self.app = app
        self.telemetry = telemetry

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        supplied = next((value.decode("latin-1") for key, value in scope.get("headers", [])
                         if key.lower() == b"x-request-id"), None)
        correlation = valid_request_id(supplied)
        tokens = (request_id.set(correlation), observer.set(self.telemetry), identifiers.set({}))
        started = perf_counter()
        status = 500
        response_started = False

        async def correlated_send(message):
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                headers = [(key, value) for key, value in message.get("headers", [])
                           if key.lower() != b"x-request-id"]
                message = {**message, "headers": headers + [(b"x-request-id", correlation.encode("ascii"))]}
            await send(message)

        try:
            await self.app(scope, receive, correlated_send)
        except Exception:
            status = 500
            if not response_started:
                await PlainTextResponse("Internal Server Error", status_code=500)(scope, receive, correlated_send)
            else:
                raise
        finally:
            try:
                route = bounded(getattr(scope.get("route"), "path", None), ROUTES)
                outcome = "failed" if status >= 500 else "rejected" if status >= 400 else "success"
                observe("http.request", outcome, started,
                        severity=logging.ERROR if status >= 500 else logging.INFO,
                        route=route, method=bounded(scope["method"], {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}),
                        status_code=status, **scope.get("path_params", {}))
                try:
                    self.telemetry.request(scope["method"], route, status, perf_counter() - started)
                except Exception:
                    pass
            finally:
                request_id.reset(tokens[0])
                observer.reset(tokens[1])
                identifiers.reset(tokens[2])
