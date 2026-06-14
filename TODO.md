What you haven't considered:
  - LangGraph checkpointer — right now graph state is in-memory and dies on restart. You need a PostgresSaver or SqliteSaver to persist runs across restarts and resume interrupted graphs after server bounce
  - LangSmith tracing — one env var (LANGCHAIN_TRACING_V2=true) gives you full node-by-node traces, token counts, and retry visibility; invaluable for debugging LLM calls
既然有 Prometheus+alertmanager 这种自动化监测工具，那我的 MCP 工具是不是可以替换为这些，然后让 agent 自行决定去查哪个自动化工具？
human escalation handler???
+Redis 分布式锁
Recovery policy should be conservative:
RECEIVED: can be re-evaluated only if raw_payload is sufficient to rebuild an AlertItem, or mark stale/failed if it was bad seed data.
RUNNING: if graph state/checkpoint is missing, rebuild initial state from DB alert and run graph.
WAITING_APPROVAL: do not run graph again; ensure there is a pending ticket and surface it in UI.
SOLVED/RESOLVED/FAILED/ESCALATED: do nothing.
lease+idempotency+fencing token+audit log
repository tickets - session.commit