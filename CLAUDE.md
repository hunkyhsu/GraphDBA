# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GraphDBA is an industrial-grade Agentic database self-healing and tuning system. The core design philosophy centers on building a strict deterministic defensive state machine that uses precise event triggers as the sole entry point for AI agent intervention.

**Key Principles:**
- Safety-first, deterministic-priority design
- Physical layer errors use deterministic repair scripts (no AI trial-and-error)
- Complex performance anomalies use multi-agent cross-validation workflows
- Mandatory DBA one-click review with absolute version rollback capability
- AI agents are orchestration engines, not exploratory experimenters

## System Architecture

### Five-Layer Architecture (Bottom-Up)

1. **Physical & Storage Layer**
   - Database kernels (PostgreSQL/MySQL)
   - WAL (Write-Ahead Logging), Undo Log
   - Volume-based snapshot mechanisms

2. **Security & Protocol Layer (MCP Gateway)**
   - Dual-stack MCP Servers (read/write isolation)
   - Read Probe MCP: READ-ONLY, row limiting, timeout circuit breaker
   - Write Execution MCP: OAuth identity passthrough, forced snapshot anchoring
   - Prevents malicious prompt injection from reaching physical database

3. **Agentic Reasoning Layer**
   - **Orchestrator/RCA Agent**: Entity extraction, workflow control
   - **Diagnostic Agent**: Metrics and log analysis
   - **Planning Agent**: Generate mitigation measures and tuning scripts
   - **Validation Agent (Critic)**: Dynamic verification using real-time physical data to eliminate hallucinations

4. **Knowledge & RAG Layer**
   - Metric-to-Text converter (transforms time-series metrics into semantic descriptions)
   - Hybrid retrieval: BM25 (lexical) + semantic vector search with RRF reranking
   - Feedback Store: Captures DBA refinements for continuous learning

5. **Application & Auditing Layer**
   - DBA review dashboard with Human-in-the-loop (HITL)
   - Snapshot/version rollback control panel
   - One-click deployment/execution switch

### Core Workflow

```
Event Trigger → [Physical Error? → Deterministic Script | Complex Anomaly? → Multi-Agent Diagnosis]
→ DBA Review → Snapshot Anchor → Execute → Health Check → [Success | Auto-Rollback]
```

## Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Agent Framework | DB-GPT (AWEL) | Native multi-agent framework for databases with sandbox execution |
| MCP Gateway | Bytebase DBHub | Lightweight multi-database MCP with built-in guardrails |
| LLM Engine | Qwen-Max / GPT-4o | Strong code reasoning and logical pruning capabilities |
| RAG & Knowledge | RAGFlow + ChromaDB | Deep document understanding, dual-path retrieval |
| Version Rollback | Undo Log + Volume Snapshot | DML rollback via Undo Log, DDL safety via storage snapshots |

## Key Design Patterns

### 1. Physical Deterministic Short-Circuit
- Page corruption, disk bad blocks, or Fatal-level crashes bypass AI reasoning
- System directly invokes backup fusion, WAL replay, or storage node isolation
- AI only monitors execution state and generates post-incident reports

### 2. Anomaly Diagnosis Tree (DAG Constraint)
- Planning Agent actions constrained by pre-configured DAG (similar to GaussMaster)
- DBAs define standard troubleshooting flowcharts
- LLM decides which branch to take in the DAG, cannot invent new steps
- Any deviation from diagnosis tree is intercepted by Orchestrator

### 3. Dynamic Closed-Loop Critic Review
- Validation Agent has permission to issue harmless observation queries (EXPLAIN, system views)
- When Diagnostic Agent produces root cause hypothesis, Validation Agent generates probe code
- Physical environment data used as counter-evidence to challenge hypotheses
- Only physically-verified root cause chains enter final DBA review report

### 4. Dual-Stack MCP Isolation Architecture
- **Read MCP**: Regular service credentials for data collection and diagnosis
- **Write MCP**: OAuth identity passthrough bound to specific DBA's system permissions
- Write MCP includes regex matching and semantic-based instruction circuit breaker (DLP)
- Any payload attempting privilege escalation or large-scale table locking is permanently rejected at protocol layer

### 5. Atomic Snapshot & MVCC Rollback Anchor
- Before applying tuning changes, system automatically injects volume snapshot or savepoint
- 5-minute health check period after changes applied
- If key business metrics degrade unexpectedly, system auto-rolls back without human intervention
- Uses `ROLLBACK TO SAVEPOINT` or snapshot restoration

## Development Guidelines

### When Working with Agent Code
- Never allow agents direct database write access without DBA approval
- All agent-generated SQL must pass through MCP gateway validation
- Implement timeout and row-limit protections for all queries
- Use MVCC and savepoints to wrap all tuning operations in rollback-capable transactions

### When Implementing MCP Servers
- Enforce strict read/write separation
- Implement identity passthrough for write operations
- Add protocol-layer guardrails: row limits, timeouts, read-only enforcement
- Use TOML/YAML for multi-database connection multiplexing

### When Building RAG Components
- Convert time-series metrics to semantic text before embedding
- Use hybrid retrieval (BM25 + semantic) with RRF reranking
- Maintain feedback store to capture DBA refinements
- Ensure citation tracking so DBAs can verify source of recommendations

### When Designing Multi-Agent Workflows
- Decompose tasks into specialized agents with narrow context windows
- Use tree-search algorithms (Tree-of-Thought) for complex diagnostics
- Implement cross-review between peer agents (e.g., CPU expert vs Lock expert)
- Constrain exploration paths within pre-defined anomaly diagnosis trees

## Manual Testing Requirements

Every phase and sub-task **must** include a `## Manual Testing` section in the corresponding code or documentation that records:

1. **Prerequisites** - What needs to be running or configured (e.g., PostgreSQL instance, env vars, Docker containers)
2. **Step-by-step test commands** - Copy-pasteable shell commands the developer can run to verify correctness
3. **Expected results** - Exact output, return values, or behaviors that confirm the task is working correctly
4. **Negative tests** - Commands that should fail or be blocked, with the expected error message/behavior
5. **Cleanup** - How to tear down any test resources

This ensures every piece of functionality can be independently verified by a human before moving to the next task. Do not mark a task as complete without providing these manual test instructions.

## Critical Safety Rules

1. **Never bypass physical deterministic repair** - For storage-layer errors, use verified scripts only
2. **Always create snapshot anchors** - Before any tuning operation, create rollback point
3. **Enforce Human-in-the-loop** - DBA must approve all structural changes
4. **Validate with physical data** - Use Critic agents to verify hypotheses against real database state
5. **Implement circuit breakers** - Timeout, row limits, and read-only modes are mandatory
6. **Use identity passthrough** - Write operations must inherit DBA's actual permissions

## References

### Key Academic Papers (2024-2026)
- AgentTune (SIGMOD 2025/2026): LLM-based database knob tuning with range pruner
- Rabbit (ICDE 2025): RAG-enabled database tuning with multi-agent domain pruning
- D-Bot (SIGMOD-Companion 2025): LLM-powered DBA copilot with group discussion mechanism
- GaussMaster (arXiv 2025): Anomaly diagnosis trees for deterministic tool orchestration
- MA-RCA (Springer 2026): Multi-agent framework for root cause analysis with hallucination suppression

### Key Open Source Projects
- **eosphoros-ai/DB-GPT**: Database multi-agent framework with AWEL workflow language
- **bytebase/dbhub**: Lightweight database MCP gateway with built-in guardrails
- **infiniflow/ragflow**: Production-grade RAG with deep document understanding and citation tracking

## Project Status

This is a research and design phase project (v1.0). The markdown document contains the theoretical foundation and architectural blueprint for implementation.
