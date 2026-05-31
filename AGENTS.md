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

- `src/graphdba/app/app.py` creates the FastAPI app and, during lifespan startup, opens read/write MCP stdio clients, creates the embedding model, creates DeepSeek LLMs, builds the LangGraph, and stores these in `app.state`.
- `POST /api/v1/alerts` accepts Alertmanager webhook payloads and starts a background graph run for each firing alert. The LangGraph `thread_id` is the alert fingerprint.
- `GET /api/v1/runs/{run_id}` returns current graph state and `next` nodes.
- `GET /api/v1/runs/{run_id}/stream` streams LangGraph events with SSE.
- `POST /api/v1/runs/{run_id}/approve` calls write MCP `approve_ticket`, updates graph state with approval fields, then resumes the graph.

### Agent Graph (`src/graphdba/agents/`)

`src/graphdba/agents/graph.py` builds a LangGraph `StateGraph` with `MemorySaver` checkpointing.

Current node order:

```text
START
  -> triage_node
  -> diagnostic_node
  -> validation_node
       -> diagnostic_node retry loop on validation failure
  -> planning_node
  -> proposing_node
  -> [INTERRUPT before execution_node]
  -> execution_node
  -> END
```

Routing is driven by `WorkflowStatus` from `src/graphdba/agents/state.py`:

- Triage: `TRIAGED` -> Diagnostic; anything else -> END.
- Diagnostic: `DIAGNOSED` -> Validation; anything else -> END.
- Validation: `VALIDATED_SUCCESS` -> Planning; `VALIDATED_FAIL` -> Diagnostic while `attempt_count < get_settings().agent.max_retries`, otherwise END.
- Planning: `PLANNED` -> Proposing; anything else -> END.
- Proposing: `PROPOSED` -> Execution; anything else -> END.
- Execution always edges to END.

Human-in-the-loop is implemented with `interrupt_before=[NodeName.EXECUTION]`. Before resume, callers should inspect `final_plan` and `ticket_id`, then inject:

```python
graph.update_state(config, {
    "approval_decision": ApprovalDecision.APPROVED,  # or REJECTED
    "human_feedback": "...",
})
```

Then resume with `graph.astream(None, config)`.

### Node Responsibilities

- `triage_node`: pure deterministic function. Validates `AlertPayload`, escalates critical physical/storage/network errors, and initializes mutable state for normal alerts.
- `DiagnosticNode`: LLM reasoning node using read MCP tools and optional HuggingFace embeddings. It lists available read tools at runtime, asks for 1-3 hypotheses, filters duplicate hypotheses, and increments `attempt_count`.
- `ValidationNode`: executes each hypothesis' read MCP validation actions, aggregates tool output, and uses chat LLM structured output to mark each hypothesis `verified`, `rejected`, or `inconclusive`.
- `PlanningNode`: uses reasoning LLM to convert verified hypotheses into a conservative `FinalPlan`; requires execution steps and exactly one of `rollback_sql` or `rollback_note`.
- `ProposingNode`: calls write MCP `propose_ticket` to stage the plan in `change_tickets`; stores returned `ticket_id`; never executes SQL.
- `ExecutionNode`: if rejected by the human, terminates as `COMPLETED` with a failure reason. If approved, calls write MCP `execute_ticket` using `ticket_id`.

### State Models

`src/graphdba/agents/state.py` is the canonical schema source.

- `AlertPayload` uses Alertmanager-style aliases: `fingerprint`, `alertname`, and `startsAt`.
- `AgentState` is the LangGraph shared `TypedDict`; nodes return partial `AgentStateUpdate`.
- `rejected_hypotheses` is `Annotated[list[dict], operator.add]`, so it appends across retry cycles.
- `current_hypotheses` is replaced each diagnostic cycle and reduced to verified hypotheses after validation.
- `WorkflowStatus` includes `TRIAGED`, `DIAGNOSED`, `VALIDATED_SUCCESS`, `VALIDATED_FAIL`, `PLANNED`, `PROPOSED`, `EXECUTED`, `COMPLETED`, `FAILED`, and `ESCALATED`. There is currently no `PENDING` value.
- `NodeName` includes `TRIAGE`, `DIAGNOSTIC`, `VALIDATION`, `PLANNING`, `PROPOSING`, and `EXECUTION`.

### Diagnostic Design Details

- `DiagnosticNode` calls `mcp_client.list_tools()` at runtime and injects tool names, descriptions, and input schemas into the prompt.
- Structured output uses `DiagnosticOutput` with `require_human_escalation`, optional `escalation_reason`, and optional hypotheses.
- Hypotheses must include non-empty `validation_actions`.
- Deduplication is embedding-based cosine similarity via `HuggingFaceEmbeddings.aembed_documents`; embeddings are normalized in `src/graphdba/config/dependencies.py`.
- Similarity threshold is `0.85`.
- Similar `REJECTED` hypotheses are blocked on retry.
- Similar `INCONCLUSIVE` hypotheses are blocked only when the proposed validation actions are identical.
- LLM calls use `llm_call_with_retry`; MCP and embedding calls use `single_external_call`.

### MCP Servers

There are two FastMCP servers launched through stdio by `src/graphdba/config/dependencies.py`.

Read server: `graphdba.mcp.server_read`

- `explain_query`
- `execute_safe_select`
- `get_pg_stat_statements`
- `get_blocking_locks`

Write server: `graphdba.mcp.server_write`

- `create_alert`
- `get_alert`
- `update_alert_status`
- `propose_ticket`
- `approve_ticket`
- `execute_ticket`

`src/graphdba/database/connection_pool.py` creates an asyncpg pool and initializes the `change_tickets` table for the write server. `ReadEnforcer` blocks non-read queries using regex validation and applies row limits. `WriteEnforcer` verifies JWT identity for approval and validates SQL syntax via PostgreSQL `PREPARE`.

### LLM and Embedding Configuration

`src/graphdba/config/dependencies.py` defines:

- `get_reasoning_llm()`: `ChatDeepSeek`, `max_tokens=3000`, `temperature=0.0`, thinking enabled. Used by Diagnostic and Planning.
- `get_chat_llm()`: `ChatDeepSeek`, `max_tokens=1000`, `temperature=0.0`, thinking disabled. Used by Validation.
- `get_embedding()`: cached `HuggingFaceEmbeddings`, default `BAAI/bge-small-en-v1.5`, normalized embeddings.
- `get_mcp_client(is_read: bool)`: async context manager for stdio MCP sessions.

`src/graphdba/app/app.py` sets `HF_HUB_OFFLINE=1`, so the embedding model must already be available locally in runtime environments that start the app.

## Mock Testing (`tests/`)

`tests/conftest.py` defines `ManagedMockClient`, which replaces real MCP `ClientSession` objects in tests.

Fixture shape:

```yaml
alert_payload:
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

- `ManagedMockClient.call_tool()` returns a plain string, while production MCP `call_tool()` returns an object with `isError` and `content`. Current agent nodes expect the production shape.
- `tests/integration/test_workflow.py` is stale against source: it references `WorkflowStatus.PENDING`, calls `build_graph()` without the required `embedding` argument, and expects pre-proposing interrupt state as `PLANNED` even though the graph now goes through `proposing_node` before interrupting before execution.
- Some unit tests construct `Hypothesis` with a removed `description` field and assert failure messages that no longer match current source.

When updating tests, align mocks to current MCP response contracts and current graph signature before adding new assertions.
