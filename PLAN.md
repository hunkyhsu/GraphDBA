# GraphDBA Implementation Plan

## Context

GraphDBA is an industrial-grade database self-healing and tuning system that uses AI agents to diagnose and resolve database issues while maintaining strict safety guarantees. The system is designed for mission-critical production environments where data integrity and availability are paramount.

**Why this project exists:**

- Traditional database monitoring tools are reactive "alarm systems" that lack closed-loop repair capabilities
- Direct LLM access to databases poses catastrophic risks (data corruption, unauthorized changes)
- Complex performance issues require multi-agent cross-validation to eliminate AI hallucinations
- DBAs need autonomous systems that enhance rather than replace human oversight

**Core Design Philosophy:**

- Physical layer errors (page corruption, disk failures) → Deterministic repair scripts (no AI trial-and-error)
- Complex anomalies (performance bottlenecks) → Multi-agent diagnosis with dynamic validation
- All structural changes → Mandatory DBA approval with atomic rollback capability
- AI agents are orchestration engines, not exploratory experimenters

**Current State:**

- Fresh project with architectural documentation (BluePrint.md, GraphDBAReport.md, CLAUDE.md)
- No code implementation yet
- Target database: PostgreSQL 14+
- Deployment: Kubernetes with CloudNativePG operator

---

## Technology Stack


| Component        | Technology                                      | Version  |
| ---------------- | ----------------------------------------------- | -------- |
| Agent Framework  | LangGraph                                       | ≥0.2.0   |
| MCP Protocol     | Python MCP SDK                                  | ≥1.0.0   |
| LLM Provider     | GPT-4o (primary), Claude 3.5 Sonnet (secondary) | Latest   |
| Database Driver  | psycopg2-binary                                 | ≥2.9.9   |
| Vector Search    | pgvector (PostgreSQL extension)                 | ≥0.5.0   |
| RAG Framework    | LangChain + RAGFlow                             | ≥0.1.0   |
| API Framework    | FastAPI                                         | ≥0.110.0 |
| State Management | PostgreSQL (prod) / SQLite (dev)                | -        |
| Authentication   | python-jose, cryptography                       | Latest   |


---

## Directory Structure to Create

```
/Users/hunkyhsu/CursorProjects/GraphDBA/
├── agents/                          # LangGraph multi-agent orchestration
│   ├── __init__.py
│   ├── state.py                     # Global State (TypedDict)
│   ├── supervisor.py                # Orchestrator/RCA Agent
│   ├── diagnostic_node.py           # Diagnostic & RAG retrieval
│   ├── critic_node.py               # Validation Agent (dynamic verification)
│   ├── planner_node.py              # Planning Agent (tuning script generation)
│   └── workflow.py                  # StateGraph compilation & checkpointer
│
├── mcp_servers/                     # MCP Server implementations
│   ├── __init__.py
│   ├── read_probe_server.py         # Read-only MCP (metrics, EXPLAIN)
│   ├── write_execute_server.py      # Write MCP (snapshot, DDL execution)
│   └── security_utils.py            # SQL injection prevention, transaction wrappers
│
├── rag/                             # Knowledge & retrieval layer
│   ├── __init__.py
│   ├── document_loader.py           # PostgreSQL manual & ticket parsing
│   ├── metric_to_text.py            # Time-series → semantic text conversion
│   └── pgvector_store.py            # Vector DB retrieval logic
│
├── api/                             # FastAPI dashboard & webhooks
│   ├── __init__.py
│   ├── main.py                      # FastAPI entry point
│   └── hitl_routes.py               # DBA approval endpoints (Approve/Reject)
│
├── config/                          # Configuration management
│   ├── __init__.py
│   ├── settings.py                  # Pydantic settings (env vars)
│   └── tools_config.json            # MCP tool registration & permissions
│
├── utils/                           # Shared utilities
│   ├── __init__.py
│   ├── logger.py                    # Structured logging
│   └── validators.py                # Input validation helpers
│
├── k8s/                             # Kubernetes deployment
│   ├── cloudnativepg_cluster.yaml   # PostgreSQL cluster definition
│   └── snapshot_class.yaml          # Volume snapshot configuration
│
├── tests/                           # Test suite
│   ├── __init__.py
│   ├── test_mcp_servers.py
│   ├── test_agents.py
│   └── test_rag.py
│
├── .env.example                     # Environment variable template
├── requirements.txt                 # Python dependencies
├── pyproject.toml                   # Project metadata (optional)
└── README.md                        # Setup & usage instructions
```

---

## Python Dependencies (requirements.txt)

```txt
# Core Agent Framework
langgraph>=0.2.0
langchain>=0.1.0
langchain-community>=0.0.20
langchain-openai>=0.0.5
langchain-anthropic>=0.1.0

# MCP Protocol
mcp>=1.0.0

# Database & Vector Search
psycopg2-binary>=2.9.9
sqlalchemy>=2.0.25
pgvector  # Note: Requires PostgreSQL extension installed separately

# LLM Providers
openai>=1.12.0
anthropic>=0.18.0
dashscope>=1.14.0  # Qwen-Max
litellm>=1.30.0    # Multi-provider abstraction

# RAG & Document Processing
chromadb>=0.4.22
pypdf>=4.0.0
python-docx>=1.1.0
unstructured>=0.12.0
sentence-transformers>=2.3.0

# API & Web Framework
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
pydantic>=2.6.0
pydantic-settings>=2.1.0

# Security & Authentication
python-jose[cryptography]>=3.3.0
cryptography>=42.0.0
python-dotenv>=1.0.0

# Utilities
pyyaml>=6.0.1
requests>=2.31.0
tenacity>=8.2.3  # Retry logic
prometheus-client>=0.19.0  # Metrics export
```

---

## Implementation Phases

### [ ] Phase 1: Project Foundation & Read-Only MCP (Week 1-2)

**Goal:** Establish project structure, security utilities, and safe read-only database access.

**Tasks:**

1. **Project Scaffolding**
  - Create all directories from structure above
  - Initialize `__init__.py` files
  - Set up `.env.example` with required variables
  - Create `requirements.txt` with dependencies
  - Set up virtual environment and install packages
2. **Security Utilities (`mcp_servers/security_utils.py`)**
  - Implement SQL injection detection (regex-based keyword blocking)
  - Create transaction wrapper: `with_readonly_transaction()`
  - Add query timeout enforcement (default: 30s)
  - Implement row limit injector (force `LIMIT 100` on SELECT)
  - Create DLP validator for sensitive data patterns
3. **Configuration Management (`config/settings.py`)**
  - Use Pydantic Settings for type-safe config
  - Load from environment variables
  - Validate database connection parameters
  - Define MCP tool permissions schema
4. **Read Probe MCP Server (`mcp_servers/read_probe_server.py`)**
  - Initialize MCP SDK server
  - Implement tools: `get_db_schema`, `get_pg_stat_statements`, `get_blocking_locks`, `explain_query`, `execute_safe_select`
  - Enforce READ-ONLY mode via `SET TRANSACTION READ ONLY`
  - Add connection pooling (max 5 connections)
5. **Logging Infrastructure (`utils/logger.py`)**
  - Structured JSON logging with trace IDs

**Verification:**

- Start Read Probe MCP server and test all tools
- Attempt `_safe_select` and confirm rejection

---

### [ ] Phase 2: RAG Layer & Knowledge Injection (Week 3-4)

**Goal:** Build multi-modal knowledge retrieval system with Metric-to-Text conversion.

**Tasks:**

1. **PostgreSQL Vector Store Setup (`rag/pgvector_store.py`)**
  - Enable `pgvector` extension
  - Create knowledge_chunks table with vector embeddings
  - Implement hybrid retrieval (semantic + lexical with RRF)
2. **Metric-to-Text Converter (`rag/metric_to_text.py`)**
  - Convert time-series data to semantic descriptions
  - Statistical analysis for spike/drop detection
3. **Document Loader (`rag/document_loader.py`)**
  - Parse PostgreSQL documentation (PDF/HTML)
  - Extract error code mappings
  - Generate embeddings and store in pgvector
4. **Feedback Store Integration**
  - Capture DBA refinements as high-confidence knowledge entries

**Verification:**

- Load sample documentation and test retrieval quality
- Test Metric-to-Text with synthetic data

---

### [ ] Phase 3: LangGraph Multi-Agent Workflow (Week 5-6)

**Goal:** Implement agent orchestration with dynamic Critic validation and HITL interrupt.

**Tasks:**

1. **State Definition (`agents/state.py`)**
  - Define `AgentState` TypedDict with all workflow fields
2. **Supervisor Node (`agents/supervisor.py`)**
  - Implement routing logic for physical errors vs complex anomalies
  - Entity extraction (instance_id, time_window, symptom)
3. **Diagnostic Node (`agents/diagnostic_node.py`)**
  - Call Read Probe MCP tools
  - Query RAG system
  - Generate root cause hypotheses
4. **Critic/Validation Node (`agents/critic_node.py`)**
  - Generate verification SQL for each hypothesis
  - Execute via Read Probe MCP
  - Prune unverified hypotheses
5. **Planner Node (`agents/planner_node.py`)**
  - Generate tuning scripts from validated root causes
6. **HITL Interrupt Node**
  - Use LangGraph's `interrupt()` mechanism
  - Persist state to checkpointer
7. **Workflow Compilation (`agents/workflow.py`)**
  - Build StateGraph with all nodes
  - Configure PostgreSQL checkpointer

**Verification:**

- Simulate alert and trace workflow execution
- Verify Critic node validates hypotheses
- Confirm workflow pauses at HITL interrupt

---

### [ ] Phase 4: Write Execution MCP & Snapshot Integration (Week 7)

**Goal:** Implement safe write operations with atomic rollback capability.

**Tasks:**

1. **Write Execute MCP Server (`mcp_servers/write_execute_server.py`)**
  - Implement OAuth2 identity passthrough
  - Tools: `create_storage_snapshot`, `execute_tuning_script`, `rollback_to_snapshot`
  - Pre-execution validation and transaction wrapping
2. **Snapshot Manager (`utils/snapshot_manager.py`)**
  - Interface with CloudNativePG snapshot API
  - Track snapshot metadata
3. **Execution Node (`agents/execution_node.py`)**
  - Sequence: snapshot → execute → health check
4. **Health Check Monitor (`utils/health_monitor.py`)**
  - Post-execution validation
  - Auto-rollback on degradation

**Verification:**

- Execute tuning script with snapshot creation
- Simulate degradation and confirm auto-rollback

---

### [ ] Phase 5: DBA Dashboard & HITL Interface (Week 8)

**Goal:** Build web interface for DBA approval and system monitoring.

**Tasks:**

1. **FastAPI Application (`api/main.py`)**
  - Initialize app with health check and webhook endpoints
  - WebSocket for real-time updates
2. **HITL Routes (`api/hitl_routes.py`)**
  - Endpoints: pending reviews, approve, reject, modify, rollback
3. **Frontend Dashboard**
  - Pending reviews table
  - Diagnosis report viewer with syntax highlighting
  - One-click approve/reject buttons

**Verification:**

- Trigger workflow and approve via dashboard
- Test reject and manual rollback flows

---

### [ ] Phase 6: End-to-End Integration & Testing (Week 9)

**Goal:** Validate complete workflow with safety guarantees.

**Tasks:**

1. **Integration Test Suite (`tests/test_integration.py`)**
  - Scenario 1: Physical error short-circuit
  - Scenario 2: Performance anomaly with full workflow
  - Scenario 3: Failed tuning with auto-rollback
2. **Security Testing**
  - SQL injection attempts
  - Privilege escalation tests
3. **Documentation**
  - Update README with setup instructions

**Verification:**

- All integration tests pass
- Security tests confirm no vulnerabilities

---

### [ ] Phase 7: Kubernetes Deployment (Week 10)

**Goal:** Deploy to Kubernetes with production reliability.

**Tasks:**

1. **CloudNativePG Cluster (`k8s/cloudnativepg_cluster.yaml`)**
  - Define PostgreSQL cluster with snapshots
2. **Application Deployment**
  - Create Dockerfile and deploy to K8s
3. **Observability**
  - Prometheus metrics and Grafana dashboards

**Verification:**

- Deploy to test cluster and verify execution
- Simulate pod failure and confirm recovery

---

### [ ] Phase 8: Knowledge Base Population (Week 11-12)

**Goal:** Populate RAG system and optimize agent performance.

**Tasks:**

1. **Knowledge Ingestion**
  - Load PostgreSQL documentation and historical tickets
2. **Anomaly Diagnosis Tree (DAG)**
  - Define standard troubleshooting flowcharts
  - Implement DAG constraints in Supervisor
3. **Agent Prompt Optimization**
  - Refine prompts with few-shot examples
4. **Feedback Loop**
  - Collect DBA modifications and update knowledge base

**Verification:**

- Test retrieval quality and DAG constraints
- Measure improvement in approval rates

---

## Success Criteria

- Read MCP blocks all DML/DDL attempts
- Critic node validates hypotheses with >90% accuracy
- Snapshot creation completes in <10 seconds
- End-to-end workflow completes in <5 minutes
- Auto-rollback triggers within 30 seconds
- DBA approval rate >70%
- Zero unauthorized database modifications
- System handles 10+ concurrent workflows

---

