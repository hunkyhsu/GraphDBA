# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Strict Constraints

- **Do not execute tests or run local scripts.** Provide implementation plans and code modifications only.
- **Do not** read or reference files in `demo/`, `rag/`, or `utils/`. Ignore all `README.md` files — their content is outdated. Focus exclusively on the Agent Graph (`src/graphdba/agents/`) and Mock Testing (`tests/`).

## Commands

This project uses `uv` for dependency management.

```bash
# Install dependencies
uv sync

# Run the integration test (end-to-end graph execution with mock MCP)
uv run python tests/test_graph.py

# Run a specific MCP server standalone (for manual inspection)
uv run -m graphdba.mcp.server_read
uv run -m graphdba.mcp.server_write
```

Configuration is loaded from a `.env` file using nested delimiter `__`. Example:
```
DATABASE__HOST=localhost
DATABASE__PORT=5432
LLM__DEEPSEEK_KEY=sk-...
AGENT__MAX_RETRIES=5
```

## Architecture

### Agent Graph (`src/graphdba/agents/`)

A LangGraph `StateGraph` that implements a multi-agent pipeline for automated PostgreSQL anomaly diagnosis. The graph is built in `src/graphdba/agents/graph.py` via `build_graph()`.

**Node execution order:**

```
START → triage_node → diagnostic_node → validation_node → planning_node
                           ↑                  |
                           └──(retry loop)────┘
                                              ↓
                                    [INTERRUPT: wait for human approval]
                                              ↓
                                       execution_node → END
```

**Routing logic** — all routing is driven by `WorkflowStatus` (a `StrEnum` in `src/graphdba/agents/state.py`):
- `TRIAGED` → proceed to Diagnostic; anything else → END
- `DIAGNOSED` → proceed to Validation; `FAILED` → END
- `VALIDATED_SUCCESS` → proceed to Planning; `VALIDATED_FAIL` → retry Diagnostic if `attempt_count < max_retries`, else END
- `PLANNED` → proceed to Execution (but graph is interrupted here); `FAILED` → END

**Human-in-the-Loop** is implemented via `interrupt_before=[NodeName.EXECUTION]` in `build_graph()`. After the graph suspends:
1. Caller reads `graph.get_state(config)` to inspect `final_plan`
2. Caller injects `approval_decision` + `human_feedback` via `graph.update_state(config, {...})`
3. Caller resumes with `graph.astream(None, config)`

**Node types:**
- `triage_node` — pure function; deterministic bypass for physical errors; initializes state
- `DiagnosticNode`, `ValidationNode`, `PlanningNode`, `ExecutionNode` — callable classes that take `llm` and/or `mcp_client` in `__init__`

**State** (`src/graphdba/agents/state.py`):
- `AgentState` is the full shared TypedDict; nodes return `AgentStateUpdate` (partial, `total=False`)
- `rejected_hypotheses` uses `Annotated[list, operator.add]` — it is append-only across retries
- `current_hypotheses` is replaced each diagnostic cycle

### DiagnosticNode — key design details

- Calls `mcp_client.list_tools()` at runtime to inject available tool descriptions into the LLM prompt
- Generates 1–3 `Hypothesis` objects with `validation_actions` (MCP tool name + payload)
- Deduplicates hypotheses both within a batch (intra) and against `rejected_hypotheses` (inter) using `difflib.SequenceMatcher` with a 0.80 similarity threshold
- An `INCONCLUSIVE` hypothesis is only blocked from retry if the exact same tools are proposed again

### MCP Servers (`src/graphdba/mcp/`)

Two separate FastMCP servers launched as subprocesses via `stdio_client`:
- `server_read.py` — read-only tools: `explain_query`, `execute_safe_select`, `get_pg_stat_statements`, `get_blocking_locks`
- `server_write.py` — write tools: `propose_ticket`, `approve_ticket`, `execute_ticket`

`src/graphdba/config/dependencies.py` manages MCP client lifecycle via `@asynccontextmanager get_mcp_client(is_read: bool)`.

### Mock Testing (`tests/`)

`ManagedMockClient` (`tests/unit/managed_mock_client.py`) replaces the real MCP `ClientSession` for testing. It is loaded from a YAML fixture file.

**YAML fixture structure** (`tests/fixtures/*.yaml`):
```yaml
alert_payload:        # matches AlertPayload field aliases (fingerprint, alertname, etc.)
  fingerprint: "..."
  alertname: "..."
  ...

mock_responses:       # keyed by MCP tool name
  get_blocking_locks:
    data: "..."       # raw string returned by call_tool()
  execute_safe_select:
    data: "..."
```

**Known flaws in the current mock** (current blocker per `architecture.md`):
1. `list_tools()` returns a hardcoded tool list, not derived from the YAML — the LLM sees tools that may not match the fixture's `mock_responses` keys
2. `call_tool()` matches only by tool name, ignoring `arguments` — cannot simulate different responses for the same tool called with different parameters
3. The fixture's `alert_payload` is never used by `test_graph.py`; the test hardcodes its own `AlertPayload` inline instead

### LLM Configuration

Two LLM instances are used (both DeepSeek, configured in `src/graphdba/config/dependencies.py`):
- `llm_reasoning` — `max_tokens=3000`, `temperature=0.0`; used by DiagnosticNode and PlanningNode
- `llm_chat` — `max_tokens=1000`, `temperature=0.0`, thinking disabled; used by ValidationNode

All LLM-calling nodes use `tenacity` retry with exponential backoff (2 attempts) and `asyncio.wait_for` timeouts (15s–50s depending on node).
