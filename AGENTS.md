# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Strict Constraints

- **Do not execute tests or run local scripts.** Provide implementation plans and code modifications only.
- **Do not** read or reference files in `demo/`, `rag/`, or `utils/`.
- Ignore all `README.md` files. Their content is outdated. There is also a misspelled `src/graphdba/agents/READNE.md`; treat it like a README and ignore it.
- Primary focus is the Agent Graph (`src/graphdba/agents/`) and Mock Testing (`tests/`). Use app/config/MCP files only when needed to understand graph wiring, runtime dependencies, or tool contracts.

## Commands

The project uses `uv` for dependency management.

```bash
# Install dependencies
uv sync

# Run tests only when explicitly allowed by the user
uv run pytest
uv run pytest tests/unit/test_diagnostic.py
uv run pytest tests/unit/test_server_read.py
uv run pytest tests/integration/test_workflow.py

# Run specific MCP servers standalone only when explicitly allowed
uv run -m graphdba.mcp.server_read
uv run -m graphdba.mcp.server_write

# Run FastAPI only when explicitly allowed
uv run uvicorn graphdba.app.app:app --reload --port 8000
```

Configuration is loaded from `.env` with nested delimiter `__`.

```env
DATABASE__HOST=localhost
DATABASE__PORT=5432
DATABASE__DB=test_db
DATABASE__USER=agent_role
DATABASE__PASSWORD=password
LLM__DEEPSEEK_KEY=sk-...
LLM__DEEPSEEK_MODEL=deepseek-v4-flash
LLM__DEEPSEEK_BASE_URL=https://api.deepseek.com
EMBEDDING__MODEL_NAME=BAAI/bge-small-en-v1.5
SECURITY__OAUTH_SECRET=...
SECURITY__MAX_QUERY_TIMEOUT_MS=15000
SECURITY__MAX_RESULT_ROWS=100
AGENT__MAX_RETRIES=5
```

`pyproject.toml` currently requires Python `>=3.14`.

## Architecture

### Runtime Entry Points

- `src/graphdba/app/app.py` creates the FastAPI app and registers an `AgentContainer` during lifespan startup.
- `src/graphdba/agents/container.py` lazily initializes expensive graph dependencies on first graph access: read MCP stdio client, embedding model, DeepSeek LLMs, `AsyncPostgresSaver`, and the compiled LangGraph.
- API modules live directly under `src/graphdba/app/api/v1/`; service-layer logic for alert ingestion lives under `src/graphdba/app/api/v1/services/`.
- `POST /api/v1/alerts` accepts Alertmanager webhook payloads, persists or reuses active alerts, applies deterministic alert policy, and schedules graph work only when the policy action is `START_AGENT`.
- Startup recovery runs from `src/graphdba/app/services/recovery.py` in a background task and scans recoverable DB alerts.
- The LangGraph `thread_id` is the persisted alert UUID string, also used as the frontend `run_id`.
- `GET /api/v1/runs/{run_id}` returns graph state and `next` nodes for graph-backed runs.
- `GET /api/v1/runs/{run_id}/stream` streams LangGraph events with SSE.
- `POST /api/v1/runs/{run_id}/approve` approves or rejects the pending database ticket and executes approved SQL through repositories. It does not resume LangGraph.

### Status Boundaries

Keep these status concepts separate. Do not collapse them into one enum.

- `AlertStatus` in `src/graphdba/database/models/alert.py` is persistent business lifecycle: `RECEIVED`, `RUNNING`, `WAITING_APPROVAL`, `SOLVED`, `RESOLVED`, `ESCALATED`, `FAILED`.
- `AgentWorkflowStatus` in `src/graphdba/agents/state.py` is graph-internal routing/result state: `DIAGNOSED`, `VALIDATED_SUCCESS`, `VALIDATED_FAIL`, `PLANNED`, `FAILED`, `ESCALATED`.
- `AlertPolicyAction` in `src/graphdba/app/api/v1/services/alerts.py` is an application orchestration decision: `START_AGENT`, `FAST_PATH_SOLVED`, `ESCALATE`.
- `TicketStatus` in `src/graphdba/database/models/ticket.py` is the change-ticket lifecycle: `PENDING`, `APPROVED`, `REJECTED`, `EXECUTING`, `SUCCESS`, `FAILED`, `ROLLED_BACK`.
- `RunLeaseStatus` in `src/graphdba/database/models/run_lease.py` represents worker ownership of graph/ticket-proposal work: `RUNNING`, `RELEASED`.

The application layer maps between these concepts. The graph should not own database alert lifecycle, the API policy should not return graph workflow statuses, and `AlertStatus.RUNNING` must not be treated as proof that a worker is alive; use run leases for liveness/ownership.

### Alert Ingestion

`src/graphdba/app/api/v1/alerts.py` is route-only and delegates webhook processing to `ingest_firing_alerts()`.

`src/graphdba/app/api/v1/services/alerts.py` owns webhook ingestion:

- It ignores non-firing Alertmanager items.
- It creates new alert rows for new active fingerprints.
- It treats repeated active fingerprints as duplicates and delegates checkpoint/lease-aware handling to recovery.

`src/graphdba/app/api/v1/services/policy.py` owns deterministic alert policy:

- `apply_alert_policy()` handles deterministic non-graph decisions. Scriptable fast-path alerts become `SOLVED`; physical/storage/network-style errors become `ESCALATED`; normal alerts become `RUNNING` and receive a graph run.

`src/graphdba/app/services/recovery.py` owns graph execution and recovery:

- `build_agent_state()` creates the initial LangGraph state with alert payload, empty hypothesis lists, no final plan, attempt count `0`, and optional `failure_reason`. It does not seed `workflow_status`.
- `run_graph_with_lease()` acquires a `run_leases` row, streams or resumes the graph, heartbeats the lease, proposes tickets after planning, syncs terminal graph failures/escalations to alert status, and releases the lease.
- `recover_alert_from_record()` decides whether to skip an active lease, resume a checkpoint, restart from alert data, propose a ticket for a planned checkpoint, sync terminal graph state, or leave `WAITING_APPROVAL` alone.
- `recover_active_alerts()` scans DB alerts with `RECEIVED`, `RUNNING`, or `WAITING_APPROVAL` status during startup recovery.
- `propose_ticket_if_planned()` turns a graph `PLANNED` result into a pending ticket and moves the alert to `WAITING_APPROVAL`. Ticket proposal is idempotent for an alert that already has a pending ticket.

### Agent Graph (`src/graphdba/agents/`)

`src/graphdba/agents/graph.py` builds a LangGraph `StateGraph` and receives its checkpointer from runtime. Production runtime uses `AsyncPostgresSaver`; tests may pass `MemorySaver`.

Current node order:

```text
START
  -> diagnostic_node
  -> validation_node
       -> diagnostic_node retry loop on validation failure
  -> planning_node
  -> END
```

Routing is driven only by `AgentWorkflowStatus`:

- Diagnostic: `DIAGNOSED` -> Validation; anything else -> END.
- Validation: `VALIDATED_SUCCESS` -> Planning; `VALIDATED_FAIL` -> Diagnostic while `attempt_count < get_settings().agent.max_retries`, otherwise END.
- Planning always edges to END after producing `PLANNED`, `ESCALATED`, or `FAILED`.

There are no graph triage, proposing, execution, interrupt, approval, or human-feedback nodes. Those system/application operations belong to FastAPI services and repositories.

### Node Responsibilities

- `DiagnosticNode`: LLM reasoning node using read MCP tools and optional HuggingFace embeddings. It lists available read tools at runtime, asks for 1-3 hypotheses, filters duplicate hypotheses, and increments `attempt_count`.
- `ValidationNode`: executes each hypothesis' read MCP validation actions, aggregates tool output, uses chat LLM structured output to mark each hypothesis `verified`, `rejected`, or `inconclusive`, and persists hypothesis evidence.
- `PlanningNode`: uses reasoning LLM to convert verified hypotheses into a conservative `FinalPlan`; requires execution steps and exactly one of `rollback_sql` or `rollback_note`.

### State Models

`src/graphdba/agents/state.py` is the canonical schema source for graph state.

- `AlertPayload` uses Alertmanager-style alias `alertname` and requires the persisted alert `id`.
- `AgentState` is a `TypedDict(total=False)` so initial state does not need graph-only fields before the first node runs.
- `rejected_hypotheses` is `Annotated[list[dict], operator.add]`, so it appends across retry cycles.
- `current_hypotheses` is replaced each diagnostic cycle and reduced to verified hypotheses after validation.
- `workflow_status` is optional until a graph node emits one.
- `failure_reason` is the terminal or diagnostic failure explanation. Do not reintroduce `terminal_message`.
- Removed graph fields: `ticket_id`, `approval_decision`, and `human_feedback`.
- `NodeName` includes only `DIAGNOSTIC`, `VALIDATION`, and `PLANNING`.

### Diagnostic Design Details

- `DiagnosticNode` calls `mcp_client.list_tools()` at runtime and injects tool names, descriptions, and input schemas into the prompt.
- Structured output uses `DiagnosticOutput` with `require_human_escalation`, optional `escalation_reason`, and optional hypotheses.
- Hypotheses must include non-empty `validation_actions`.
- Deduplication is embedding-based cosine similarity via `HuggingFaceEmbeddings.aembed_documents`; embeddings are normalized in dependency setup.
- Similarity threshold is `0.85`.
- Similar `REJECTED` hypotheses are blocked on retry.
- Similar `INCONCLUSIVE` hypotheses are blocked only when the proposed validation actions are identical.
- LLM, MCP, and embedding calls are timeout/retry wrapped.

### MCP and Repositories

- The graph runtime currently opens the read MCP client only.
- Read MCP tools used by the graph include `explain_query`, `execute_safe_select`, `get_pg_stat_statements`, and `get_blocking_locks`.
- Write MCP server code may still exist, but current API approval and ticket execution flows use SQLAlchemy repositories directly.
- `src/graphdba/database/repositories/alerts.py` owns alert persistence, duplicate active-fingerprint lookup, dashboard stats, and status updates.
- `src/graphdba/database/repositories/run_leases.py` owns acquisition, heartbeat, and release of per-alert graph work leases.
- `src/graphdba/database/repositories/tickets.py` owns ticket proposal, draft updates, approval/rejection, execution, rollback attempt handling, and list/detail queries.

### LLM and Embedding Configuration

`src/graphdba/config/dependencies.py` defines:

- `get_reasoning_llm()`: `ChatDeepSeek`, `max_tokens=3000`, `temperature=0.0`, thinking enabled. Used by Diagnostic and Planning.
- `get_chat_llm()`: `ChatDeepSeek`, `max_tokens=1000`, `temperature=0.0`, thinking disabled. Used by Validation.
- `get_embedding()`: cached `HuggingFaceEmbeddings`, default `BAAI/bge-small-en-v1.5`, normalized embeddings.
- `get_mcp_client(is_read: bool)`: async context manager for stdio MCP sessions.

`src/graphdba/config/dependencies.py` creates the embedding model lazily through `get_embedding()`. If deployments require offline HuggingFace behavior, configure that explicitly in the runtime environment.

## Frontend Notes

- Frontend code lives under `frontend/`.
- Keep the existing application style: dense dashboard/tool UI, restrained cards, left sidebar navigation, and `lucide-react` icons.
- The run page should show the current graph stages only: Diagnostic, Validation, Planning. Triage, approval, and execution are application/database phases, not graph stages.
- Approval buttons call `POST /api/v1/runs/{run_id}/approve`; they should be enabled only when the alert/ticket flow is waiting for approval.

## Mock Testing (`tests/`)

`tests/conftest.py` defines `ManagedMockClient`, which replaces real MCP `ClientSession` objects in tests.

Fixture shape:

```yaml
alert_payload:
  id: "..."
  fingerprint: "..."
  alertname: "..."
  instance: "..."
  severity: "high"
  status: "firing"
  summary: "..."
  description: "..."
  startsAt: "..."
  raw_payload: {}

tool_descriptions:
  get_blocking_locks: "..."

mock_responses:
  get_blocking_locks:
    data: "..."
```

Current mock behavior:

- `list_tools()` derives tools from fixture `mock_responses` keys filtered by hardcoded read/write allowlists.
- `call_tool()` returns fixture data by tool name only and ignores arguments.
- `load_alert_payload()` reads `alert_payload` from a fixture.

Known alignment issues to fix before trusting integration coverage:

- `ManagedMockClient.call_tool()` returns a plain string, while production MCP `call_tool()` returns an object with `isError` and `content`. Current validation code expects the production shape.
- Integration tests that exercise the full graph require LLM credentials and should not be run unless explicitly allowed by the user.
- When updating tests, align mocks to current MCP response contracts, current `build_graph()` signature, and the current graph order without triage/proposing/execution nodes.
