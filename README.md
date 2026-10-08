# Enterprise Service Assurance & Resolution Platform

An agentic AI prototype for telecom service assurance. It collects operational evidence for a cell and time window, analyzes KPI degradation, correlates alarms, configuration changes, and tickets, ranks root-cause hypotheses, and can enrich the result with guidance retrieved from Nokia and 3GPP documentation.

The repository currently implements **evidence collection, weighted RCA analysis, conditional LangGraph supervision, natural-language query parsing, optional RAG recommendations, a governed corrective-action simulator, and an API/operator dashboard**. Production identity integration, live network adapters, and cloud deployment remain planned work.

## Project status

| Capability | Status | Notes |
|---|---|---|
| Synthetic telecom dataset | Complete | 120 cells, 345,600 KPI samples, 1,168 alarms, 290 changes, and 240 tickets |
| Scenario validation | Complete | 63 injected scenarios across five incident types |
| PostgreSQL schema and loading | Complete | Inventory, KPI, alarm, change, and ticket tables |
| Natural-language query parsing | Complete | Cell/site extraction and deterministic time-window resolution |
| Operational evidence collection | Complete | CSV and PostgreSQL backends |
| KPI and event analysis | Complete for prototype | Two-hour KPI baseline, metric deltas, event correlation, and timeline |
| RCA hypothesis ranking | Complete for prototype | Weighted KPI, alarm-onset, change, and ticket evidence for five incident classes |
| Knowledge-base ingestion and retrieval | Complete | 9 Nokia/3GPP PDFs, 3,554 indexed chunks in the prepared Qdrant store |
| Grounded recommendations | Complete for prototype | Structured LLM answer with retrieved document sources |
| Agent supervisor and dynamic routing | Complete for prototype | Routes only to agents whose evidence is available |
| Simulated corrective-action loop | Complete for prototype | Plan → approval → simulation → verification → rollback, with JSONL audit events |
| API and operator dashboard | Complete for prototype | FastAPI, API-key guard, SQLite state, action controls, and OpenAPI docs |
| Production security and AWS deployment | Planned | Enterprise identity, RBAC, secrets management, and cloud infrastructure are not implemented |

## Architecture

### End-to-end component architecture

```mermaid
flowchart TB
    subgraph Sources[Source and preparation layer]
        GEN[Synthetic telecom data generation]
        PDF[Nokia and 3GPP PDF documents]
        GEN --> CSV[(Operational CSV files)]
        PDF --> INGEST[PDF loading, metadata, chunking, and embeddings]
    end

    subgraph Storage[Data and persistence layer]
        PG[(PostgreSQL<br/>inventory, KPIs, alarms, changes, tickets)]
        QD[(Qdrant<br/>technical document chunks)]
        STATE[(SQLite<br/>incidents and action plans)]
        AUDIT[(JSONL<br/>append-only action events)]
        CSV -->|CSV loader| PG
        INGEST --> QD
    end

    subgraph Channels[Operator and integration channels]
        CLI[Python CLI]
        UI[Browser operator dashboard]
        DOCS[OpenAPI interface]
        CLIENT[External API client]
    end

    subgraph Interface[Application interface layer]
        API[FastAPI service]
        AUTH[X-API-Key guard]
        STATIC[Static dashboard delivery]
        UI --> STATIC --> API
        DOCS --> API
        CLIENT --> AUTH --> API
        CLI --> INPUT
    end

    subgraph Understanding[Request understanding]
        INPUT{Input mode}
        PARSER[LLM filter parser<br/>gpt-4o-mini]
        TIME[Deterministic time resolver]
        INPUT -->|Cell plus bounded window| GRAPH
        INPUT -->|CLI natural-language query| PARSER --> TIME --> GRAPH
        API -->|Structured cell and window| GRAPH
        API -->|Chat message| PARSER
    end

    subgraph Orchestration[LangGraph assurance workflow]
        GRAPH[Collect evidence]
        SUP[Supervisor and dispatcher]
        KPI[KPI agent<br/>means, baseline, deltas]
        ALARM[Alarm agent<br/>overlap, cause mapping, onset]
        CONFIG[Configuration agent<br/>preceding relevant changes]
        TICKET[Ticket agent<br/>supporting text signals]
        ASSEMBLE[Evidence assembler and timeline]
        RCA[Weighted RCA engine<br/>ranked candidates and confidence share]

        GRAPH --> SUP
        SUP -->|When KPI data exists| KPI
        SUP -->|When alarms exist| ALARM
        SUP -->|When changes exist| CONFIG
        SUP -->|When tickets exist| TICKET
        KPI --> ASSEMBLE
        ALARM --> ASSEMBLE
        CONFIG --> ASSEMBLE
        TICKET --> ASSEMBLE
        ASSEMBLE --> RCA
    end

    CSV -->|Default evidence backend| GRAPH
    PG -->|Optional evidence backend| GRAPH

    subgraph Knowledge[Optional RAG enrichment]
        QUERY[Cause-aware technical query]
        DENSE[OpenAI dense embedding search]
        BM25[Local BM25 search over Qdrant payloads]
        MERGE[Merge, deduplicate, and noise filter]
        RERANK[Cross-encoder reranker]
        ANSWER[Structured grounded answer<br/>gpt-4.1-mini]
        QUERY --> DENSE
        QUERY --> BM25
        DENSE --> MERGE
        BM25 --> MERGE --> RERANK --> ANSWER
        QD --> DENSE
        QD --> BM25
    end

    RCA -->|RAG enabled| QUERY
    RCA --> RESULT[Structured incident result]
    ANSWER --> RESULT
    RESULT --> API
    RESULT --> CLI
    API --> STATE

    subgraph Resolution[Governed simulated resolution]
        PLAN[Build reversible action plan]
        WAIT{Explicit approval?}
        SIM[Simulate projected KPI effect]
        VERIFY{Recovery checks pass?}
        COMPLETE[Mark completed]
        ROLLBACK[Restore original projected metrics]

        PLAN --> WAIT
        WAIT -->|No| PENDING[Awaiting approval]
        WAIT -->|Yes| SIM --> VERIFY
        VERIFY -->|Yes| COMPLETE
        VERIFY -->|No| ROLLBACK
    end

    RESULT -->|Action requested| PLAN
    API -->|Persist exact plan and approval state| STATE
    PLAN --> AUDIT
    WAIT --> AUDIT
    SIM --> AUDIT
    VERIFY --> AUDIT
    ROLLBACK --> AUDIT
```

The solid paths above are implemented. Qdrant and model calls are optional; the default CLI and API analysis path uses the bundled CSV evidence and does not require external services.

### Runtime incident-analysis sequence

```mermaid
sequenceDiagram
    autonumber
    actor Operator
    participant Channel as CLI / Dashboard / API
    participant Service as FastAPI or CLI entry point
    participant Graph as LangGraph supervisor
    participant Evidence as CSV or PostgreSQL
    participant Agents as Specialist evidence agents
    participant RCA as Weighted RCA engine
    participant Retriever as Qdrant + hybrid retriever
    participant Model as OpenAI model
    participant State as SQLite / JSONL

    Operator->>Channel: Submit cell ID and bounded time window
    Channel->>Service: Validated request
    Service->>Graph: Invoke assurance state
    Graph->>Evidence: Load incident and surrounding evidence windows
    Evidence-->>Graph: KPIs, baseline, alarms, changes, tickets
    Graph->>Graph: Select agents for available evidence
    loop Each selected agent
        Graph->>Agents: Analyze assigned evidence type
        Agents-->>Graph: Typed findings
    end
    Graph->>RCA: Assemble timeline and score candidates
    RCA-->>Graph: Ranked causes, evidence, recommendation, confidence share
    opt RAG enabled
        Graph->>Retriever: Retrieve guidance for candidate causes
        Retriever->>Model: Documents plus operational evidence
        Model-->>Graph: Structured grounded recommendation
    end
    Graph-->>Service: Structured incident result
    Service->>State: Persist incident when called through API
    Service-->>Channel: Return analysis and incident ID
    Channel-->>Operator: Display evidence and proposed next action
```

### Corrective-action lifecycle

```mermaid
stateDiagram-v2
    [*] --> NoAction: no supported cause
    [*] --> Planned: supported RCA candidate
    Planned --> AwaitingApproval: persist exact reversible plan
    AwaitingApproval --> AwaitingApproval: no approval supplied
    AwaitingApproval --> Simulating: operator identity approves plan
    Simulating --> Verifying: calculate projected KPI response
    Verifying --> Completed: recovery thresholds pass
    Verifying --> RolledBack: recovery thresholds fail
    Completed --> Completed: repeated approval returns stored result
    RolledBack --> RolledBack: repeated approval returns stored result
    NoAction --> [*]
    Completed --> [*]
    RolledBack --> [*]
```

Planning, approval, simulation, verification, and rollback emit audit events. API-created plans are also stored in SQLite, so approval always applies to the exact plan reviewed by the operator. The simulator changes only projected metrics and cannot modify a network element.

### Local deployment architecture

```mermaid
flowchart LR
    BROWSER[Browser<br/>operator dashboard]
    APICLIENT[API client]
    CLILOCAL[Local CLI]

    subgraph Docker[Docker Compose network]
        APP[Application container<br/>FastAPI + LangGraph + dashboard<br/>port 8000]
        POSTGRES[(PostgreSQL 17<br/>port 5432)]
        QDRANT[(Qdrant<br/>ports 6333 and 6334)]
        APP --> POSTGRES
        APP --> QDRANT
    end

    subgraph Host[Host-mounted state]
        RUNTIME[(data/runtime<br/>SQLite + JSONL audit)]
        PGVOL[(docker/postgres_data)]
        QDVOL[(docker/qdrant_data)]
    end

    OPENAI[OpenAI API<br/>parser, embeddings, answer generation]
    MODEL[Sentence Transformers model registry<br/>first reranker download]

    BROWSER -->|HTTP| APP
    APICLIENT -->|HTTP + X-API-Key| APP
    CLILOCAL --> POSTGRES
    CLILOCAL --> QDRANT
    APP --> RUNTIME
    POSTGRES --> PGVOL
    QDRANT --> QDVOL
    APP -. optional HTTPS .-> OPENAI
    APP -. first use .-> MODEL
```

The Docker topology is suitable for local development and demonstration. PostgreSQL and Qdrant ports are exposed to the host, credentials are development defaults, and the application uses a shared API key. A production deployment needs private networking, managed secrets, enterprise identity/RBAC, TLS, managed persistence, backups, monitoring, and separate scaling policies.

### Architecture responsibilities

| Layer | Components | Responsibility |
|---|---|---|
| Channels | CLI, conversational dashboard, OpenAPI, API clients | Ask natural-language questions, inspect evidence, review and approve plans |
| Interface | FastAPI, static UI, API-key dependency | Validate requests, protect APIs, persist and return results |
| Understanding | LLM parser, deterministic time resolver | Convert supported natural language into structured filters |
| Evidence | CSV store, PostgreSQL, SQL tools | Supply KPI, alarm, change, ticket, and inventory records |
| Orchestration | LangGraph supervisor and dispatcher | Select and run only the specialist agents with available evidence |
| Analysis | KPI, alarm, configuration, and ticket agents | Normalize evidence and produce specialist findings |
| RCA | Weighted deterministic scorer | Rank explainable hypotheses and attach supporting evidence |
| Knowledge | Qdrant, dense/BM25 retrieval, reranker, LLM | Add cited technical guidance without replacing operational evidence |
| Resolution | Action catalog and simulator | Plan reversible actions, require approval, project KPI effects, verify, and roll back |
| State and audit | SQLite and JSONL | Persist API incidents, exact action plans, decisions, and lifecycle events |
| Runtime | Docker Compose, application image | Run the application, PostgreSQL, and Qdrant locally |

### Current workflow

1. Accept a cell ID with a bounded time window, or parse a natural-language query.
2. Load incident KPI samples plus a two-hour pre-incident baseline.
3. Let the supervisor select KPI, alarm, configuration, and ticket agents based on the evidence available.
4. Find alarms active during the incident, changes from the preceding two hours, and tickets up to two hours after the incident.
5. Calculate KPI means and baseline deltas and build a chronological event timeline.
6. Rank supported RCA candidates using KPI breaches, alarm type and onset alignment, relevant changes, and ticket text.
7. When `--rag` is enabled, retrieve related Nokia/3GPP passages and generate a structured, evidence-grounded recommendation.
8. When `--simulate-action` is enabled, build a reversible plan, wait for explicit approval, simulate its KPI effect, verify the expected recovery, and roll back a failed verification.

Incident ranges are start-inclusive and end-exclusive. An alarm raised before the requested range is included when it remained active inside the range. A configuration change supports a regression hypothesis only when it occurred at or before incident start; timing is treated as supporting evidence, not proof of causation.

## Supported RCA classes

| RCA class | Primary prototype signals |
|---|---|
| `CONGESTION` | Mean downlink PRB utilization above 85% |
| `RADIO_INTERFERENCE` | Mean SINR below 12 dB or RSRP below -95 dBm |
| `TRANSPORT_DEGRADATION` | Mean latency above 40 ms or packet loss above 1% |
| `CELL_OUTAGE` | Mean availability below 50% |
| `CONFIGURATION_REGRESSION` | Handover success below 93% or call-drop rate above 2%, with recent changes reported separately |

These thresholds are heuristics designed for the included synthetic dataset. They are investigation aids, not production policy or confirmed RCA logic.

## Repository layout

```text
telecom_closed_loop_ai/
├── data/
│   ├── knowledge_base/             # Nokia and 3GPP PDFs
│   └── telecom_data/               # Inventory, KPI, alarm, change, ticket, and evaluation CSVs
├── docker/
│   ├── docker-compose.yml          # PostgreSQL and Qdrant services
│   ├── postgres_data/              # Local persistent database volume
│   └── qdrant_data/                # Local persistent vector-store volume
├── scripts/
│   ├── create_postgres_schema.py   # Create relational tables and indexes
│   ├── load_csv_to_postgres.py     # Load prototype CSVs into PostgreSQL
│   ├── ingest_knowledge_base.py    # Chunk, embed, and ingest PDFs into Qdrant
│   ├── run_assurance.py            # Main CLI and scenario evaluation entry point
│   └── validate_scenarios.py       # Validate injected evidence patterns
├── src/
│   ├── actions/simulator.py        # Governed action planning, simulation, verification, and rollback
│   ├── analysis/incident.py        # Evidence store, specialist analysis, timeline, and RCA scoring
│   ├── api/                         # FastAPI service and browser dashboard
│   ├── database/postgres.py        # PostgreSQL connection and query helper
│   ├── query/                      # Query schema, LLM parsing, and time resolution
│   ├── rag/                        # Hybrid retrieval, reranking, and grounded answers
│   ├── services/incident_context.py
│   ├── tools/                      # KPI, alarm, configuration, and ticket SQL tools
│   └── workflows/assurance.py      # Conditional LangGraph supervisor and specialist agents
├── tests/                           # Workflow, action-loop, persistence, and API tests
├── Dockerfile                       # API/dashboard application image
└── requirements.txt
```

## Prerequisites

- Python 3.10 or newer
- `pip` and a Python virtual environment
- Docker with Docker Compose for PostgreSQL and Qdrant workflows
- An OpenAI API key for natural-language parsing, embeddings, and grounded answers
- Network access on the first reranker run so Sentence Transformers can obtain `cross-encoder/ms-marco-MiniLM-L-6-v2`

The default CSV workflow runs locally without Docker, Qdrant, or model credentials.

## Quick start: offline RCA

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Analyze one incident directly from the supplied CSV files:

```bash
python -m scripts.run_assurance \
  --cell CELL_028_1 \
  --start "2026-08-05 07:00:00" \
  --end "2026-08-05 10:00:00"
```

The command returns JSON containing:

- workflow status and the highest-ranked likely cause;
- all supported RCA candidates and their evidence;
- incident and baseline KPI aggregates;
- metric deltas;
- correlated alarms, changes, and tickets;
- a chronological event timeline;
- explicit analysis limitations.

If the cell/time window contains no KPI data, the result is marked `insufficient_evidence` and no cause is claimed.

## Evaluate all 63 scenarios

```bash
python -m scripts.run_assurance --evaluate
```

The evaluation reads `data/telecom_data/evaluation/scenario_truth.csv` and writes the detailed result to `data/telecom_data/evaluation/rca_evaluation.json`.

Current offline result:

| Metric | Result |
|---|---:|
| Scenarios | 63 |
| Expected cause ranked first | 63/63 (100%) |
| Expected cause included among candidates | 63/63 (100%) |

Scenario distribution:

| Type | Count |
|---|---:|
| Congestion | 18 |
| Radio interference | 15 |
| Transport degradation | 12 |
| Configuration regression | 10 |
| Cell outage | 8 |

Scenario labels are used only to score the final predictions; they are not supplied to the RCA workflow. This result measures performance on the synthetic scenarios used to design the prototype and should not be interpreted as production-network accuracy.

## Run automated tests

```bash
python -m unittest discover -s tests
```

The current suite checks no-data handling, invalid time windows, alarm overlap behavior, outage prioritization, configuration-change timing, supervisor routing, overlapping-scenario disambiguation, approval enforcement, successful verification, and rollback.

## API and operator dashboard

Set an API key and start the local service:

```bash
export SERVICE_API_KEY="replace-with-a-local-secret"
uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000` for the conversational operator dashboard or `http://127.0.0.1:8000/docs` for the generated OpenAPI interface. Enter the same API key in the dashboard, then ask a question containing a cell ID and bounded August 2026 time window. The sidebar includes five known incident questions that can be sent with one click.

The service exposes:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Public liveness and version check |
| `POST` | `/api/chat` | Parse a natural-language question, run RCA, and return a conversational answer |
| `POST` | `/api/incidents` | Run and persist an incident analysis |
| `GET` | `/api/incidents/{incident_id}` | Retrieve analysis and action history |
| `POST` | `/api/incidents/{incident_id}/actions` | Create an action plan in `awaiting_approval` state |
| `POST` | `/api/actions/{action_id}/approve` | Approve the exact persisted plan and run its simulation |

All `/api/*` calls require the API key in `X-API-Key`. For example:

```bash
curl -X POST http://127.0.0.1:8000/api/incidents \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${SERVICE_API_KEY}" \
  -d '{
    "cell_id": "CELL_028_1",
    "start_time": "2026-08-05 07:00:00",
    "end_time": "2026-08-05 10:00:00",
    "backend": "csv",
    "rag": false
  }'
```

Incident analyses and action-plan state are stored in `data/runtime/incidents.db`. Repeated approval of a completed action is idempotent and returns the stored result. The default API key is `development-only` for local convenience; always set `SERVICE_API_KEY` outside a local demo.

The chat response includes a readable explanation, ranked evidence, the parsed cell/time filters, and an incident ID. The browser keeps the latest incident ID so a follow-up such as `What action do you recommend?` reuses the preceding cell and time window. A question that names a new cell or window starts a new investigation context.

## PostgreSQL workflow

Start the complete Docker stack—application, PostgreSQL, and Qdrant:

```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml ps
```

The dashboard is then available at `http://localhost:8000`. Docker Compose uses the development API key `development-only`; replace it before using the service outside an isolated local environment.

Create the database schema and load the supplied CSV data:

```bash
python -m scripts.create_postgres_schema
python -m scripts.load_csv_to_postgres
```

Then run RCA against PostgreSQL:

```bash
python -m scripts.run_assurance \
  --backend postgres \
  --cell CELL_028_1 \
  --start "2026-08-05 07:00:00" \
  --end "2026-08-05 10:00:00"
```

The application database layer accepts these environment variables:

| Variable | Default |
|---|---|
| `POSTGRES_HOST` | `localhost` |
| `POSTGRES_PORT` | `5432` |
| `POSTGRES_DB` | `telecom_db` |
| `POSTGRES_USER` | `telecom_user` |
| `POSTGRES_PASSWORD` | `telecom_password` |

Application runtime variables:

| Variable | Default |
|---|---|
| `SERVICE_API_KEY` | `development-only` |
| `INCIDENT_DB_PATH` | `data/runtime/incidents.db` |
| `ACTION_AUDIT_PATH` | `data/runtime/action_audit.jsonl` |

The schema creation and CSV loading scripts currently use the Docker development credentials directly. The loader truncates each target table before importing its CSV, so it should be used only with the disposable prototype database.

Stop the services without deleting their persisted data:

```bash
docker compose -f docker/docker-compose.yml down
```

## Natural-language queries

Create a `.env` file or export the required credential:

```dotenv
OPENAI_API_KEY=your-api-key
```

Then run a query that resolves to a cell and a bounded time window:

```bash
python -m scripts.run_assurance \
  --query "What happened to CELL_028_1 around 2026-08-05 08:30?"
```

Time handling rules:

- `at <time>` creates a 30-minute window: 15 minutes before and after.
- `around <time>` creates a 60-minute window: 30 minutes before and after.
- `between <start> and <end>` uses the extracted bounds.
- relative expressions such as `last 2 hours` use the local process time as the reference.
- `before` and `after` are parsed, but the assurance CLI currently requires both start and end bounds before execution.

The query parser uses `gpt-4o-mini`. Explicit `--cell`, `--start`, and `--end` arguments are preferable for reproducible offline evaluation.

## Knowledge base and RAG

The knowledge base contains nine Nokia/3GPP PDFs covering LTE/5G measurements, KPI definitions, statistics, service assurance, data collection, and troubleshooting.

Set the model and Qdrant configuration:

```dotenv
OPENAI_API_KEY=your-api-key
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=telecom_knowledge_base
```

Inspect PDF extraction and telecom term coverage:

```bash
python -m scripts.check_knowledge_base
```

Preview page splitting and metadata without modifying Qdrant:

```bash
python -m scripts.prepare_rag_documents
```

Rebuild the Qdrant collection:

```bash
python -m scripts.ingest_knowledge_base
```

> **Warning:** ingestion uses `force_recreate=True`, which replaces the existing collection with the same name. It also calls the OpenAI embedding API and may incur usage charges.

Run standalone RAG retrieval and generation:

```bash
python -m scripts.test_retrieval
python -m scripts.test_rag
```

Run the assurance workflow with grounded technical recommendations:

```bash
python -m scripts.run_assurance \
  --cell CELL_028_1 \
  --start "2026-08-05 07:00:00" \
  --end "2026-08-05 10:00:00" \
  --rag
```

The RAG path performs dense retrieval with `text-embedding-3-small`, local BM25 retrieval over Qdrant payloads, deduplication, cross-encoder reranking, noise filtering, and structured generation with `gpt-4.1-mini`. Generated answers include the document name, page, category, technology, chunk ID, and retrieval scores for the supporting sources.

## Simulated corrective-action loop

Generate a plan without approving it:

```bash
python -m scripts.run_assurance \
  --cell CELL_028_1 \
  --start "2026-08-05 07:00:00" \
  --end "2026-08-05 10:00:00" \
  --simulate-action
```

The response contains `action_loop.status: awaiting_approval`, the proposed action, parameters, risk, expected outcome, and `approval_required: true`. No action simulation runs at this stage.

Approve and execute the local simulation by supplying an operator identity:

```bash
python -m scripts.run_assurance \
  --cell CELL_028_1 \
  --start "2026-08-05 07:00:00" \
  --end "2026-08-05 10:00:00" \
  --simulate-action \
  --approve-action \
  --approved-by operator@example.com
```

The simulator maps each supported cause to a reversible prototype action:

| Cause | Simulated action | Verification |
|---|---|---|
| Congestion | Adjust load balancing | Downlink PRB below 85% |
| Radio interference | Apply interference mitigation | SINR at least 12 dB or RSRP at least -95 dBm |
| Transport degradation | Reroute transport path | Latency at most 40 ms and packet loss at most 1% |
| Cell outage | Restart cell service | Availability at least 99% |
| Configuration regression | Roll back recent configuration | Handover success at least 93% and call drops at most 2% |

Audit events are appended to `data/runtime/action_audit.jsonl` by default. Use `--audit-file <path>` to select another location. Events cover planning, approval, simulation, verification, completion state, and rollback. The simulator modifies projected metrics only; it does not alter source CSVs, PostgreSQL records, Qdrant, or a network element.

## Utility scripts

The `scripts/` directory also contains focused checks for the database connection, SQL tools, query parser, time resolver, incident context, retrieval, and RAG response. Run them as modules from the project root, for example:

```bash
python -m scripts.test_time_resolver
python -m scripts.test_kpi_tool
python -m scripts.test_alarm_tool
python -m scripts.test_config_tool
python -m scripts.test_ticket_tool
python -m scripts.test_incident_context
```

Most of these are diagnostic scripts that print results. The repeatable assertion-based suite is under `tests/`.

## Data notes

The supplied operational data is synthetic and covers August 2026 at 15-minute KPI intervals. It is suitable for demonstrations and controlled evaluation, but it does not model all real-network dependencies, seasonality, topology effects, maintenance windows, or vendor-specific behavior.

The optional `data/hugging_face_data/` files and `test.ipynb` are exploratory assets. They are not part of the main assurance CLI path.

## Current limitations

- RCA ranking combines fixed thresholds with alarm-onset alignment, configuration timing, and ticket keywords; it does not yet learn baselines per cell, hour, weekday, band, or technology.
- Multiple failure modes can breach the same KPIs, producing ambiguous candidates.
- Alarm severity, detailed parameter semantics, topology, and free-form ticket meaning are not deeply modeled.
- The LangGraph supervisor routes by evidence availability; it does not yet use an LLM planner or retry/recovery policy.
- RAG provides investigation guidance; retrieved documentation does not by itself confirm an operational root cause.
- Model-backed paths require network access and credentials and have not been included in the offline 63-scenario accuracy figure.
- Corrective actions alter projected metrics only; there is no network-element or digital-twin adapter.
- SQLite incident/action state and the JSONL audit are single-instance prototype storage; there is no enterprise identity, role-based authorization, multi-user concurrency design, observability, or deployment automation.

## Roadmap to the end-to-end closed loop

1. **Improve evidence scoring:** add severity, detailed parameter relevance, topology, technology-aware thresholds, seasonal baselines, and calibrated confidence.
2. **Add a digital twin:** replace formula-based projected metrics with a stateful simulator that models neighboring cells, traffic migration, and delayed KPI response.
3. **Strengthen governance:** add action allowlists, maintenance windows, risk-based approvers, policy-as-code, and tamper-evident audit storage.
4. **Evolve the product surface:** add incident search, live progress, citation views, topology visualization, and enterprise identity to the existing API/dashboard.
5. **Production hardening:** replace SQLite with a transactional service database and add secrets management, RBAC, retries, tracing, metrics, cost controls, integration tests, CI/CD, and AWS deployment.
6. **Extend evaluation:** measure cause ranking, evidence precision, recommendation grounding, unsafe-action rejection, recovery success, rollback correctness, latency, and cost on unseen scenarios.

## Safety and intended use

This project is a prototype for research and demonstration. RCA outputs are hypotheses that require operator review. Do not connect corrective-action code to production network elements until authentication, authorization, approval policy, audit logging, idempotency, verification, rollback, and vendor-specific integration tests are in place.
