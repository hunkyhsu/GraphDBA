# 项目初始化与架构蓝图 (Project Initialization & Architecture Blueprint)

1 项目的愿景和系统的边界 (Project Vision & Boundaries)
项目愿景：为核心生产环境打造一个“主动式、确定性、高置信度”的数据库自愈与调优系统。系统通过构建严格的物理层防御状态机与 Multi-Agent 交叉验证工作流，在保障数据安全性与高可用性的前提下，实现从物理故障的自愈到复杂性能瓶颈的闭环调优。

系统边界：

明确支持的核心引擎：本系统的底层管控与调优目标明确且唯一针对 PostgreSQL (建议 v14+)。

确定性物理自愈：仅对有明确签名的底层错误（如 Page 损坏）执行预设恢复脚本，AI 仅作编排，绝不干预物理执行逻辑。

受控诊断与交互：复杂异常由多智能体工作流诊断；AI 与数据库的交互必须通过带有强防护栏（强制只读、限流熔断）的 MCP Server 进行隔离。

不可触碰的红线：严禁 AI 在无 DBA 审批的情况下对现网进行 DDL/Knob 修改；严禁 MCP 凭证越权共享；严禁在未成功创建底层回滚快照前执行任何修改动作。

2 技术栈和核心的依赖 (Tech Stack & Core Dependencies)
为了支撑上述边界并发挥最大效能，系统的核心技术栈规划如下：

基础设施与持久化层 (Infrastructure & Persistence)

运行环境：Kubernetes 云原生集群（利用 K8s 提供的故障转移与动态扩缩容能力，保障系统自身的高可用）。

目标数据库支持：基于 CloudNativePG Operator 部署的 PostgreSQL 集群。

底层快照与回退：利用 CloudNativePG 提供的 Volume Snapshot API (CSI) 实现存储卷级别的微秒级快照 ``，作为 DBA 授权执行高危调优前的物理托底防线。

模型上下文协议与安全网关 (MCP Security Gateway)

协议层选型：基于官方 Python MCP SDK 开发专属的 PostgreSQL MCP Server。

安全依赖：双栈物理隔离（读探针与写执行）。写执行服务端强制集成 OAuth2 身份透传，并在底层利用原生事务封装（SET TRANSACTION READ ONLY）实现硬性安全屏障。

智能体图编排层 (Agentic Graph Orchestration)

开发框架：LangGraph（原生支持复杂循环图结构、状态传递与打断机制）``。

状态持久化：使用 PostgreSQL 或 SQLite 作为 LangGraph 的 Checkpointer ``，用于保存上下文并实现 DBA 审批前的工作流安全挂起 (Human-in-the-loop)。

核心大语言模型：GPT-4o 或 Claude 3.5 Sonnet（作为节点的核心推理大脑），配合开源代码模型进行 SQL 的二次验证。

多模态知识库与 RAG 层 (Knowledge & Retrieval)

向量数据库：pgvector 扩展 ``（直接运行在专用的 PostgreSQL 实例上，减少技术栈碎片化，利用原生 SQL 进行关系与语义混合检索）。

文档解析与增强引擎：RAGFlow，用于深度解析非结构化的 PostgreSQL 官方排错手册与企业历史工单，并支持结构化指标（Metrics-to-Text）的语义对齐。

3 MCP Server 接口的定义 (MCP Interface Definitions)
MCP Server 将以标准化的 JSON Schema 格式向 LangGraph Agent 动态暴露工具链 [48]：

只读探针 MCP (Read-Only Probe - 供 Agent 查询)

get_db_schema(table_names: List[str]): 返回目标表的 DDL、列属性与关联的外键。

get_pg_stat_statements(limit: int, min_duration_ms: int): 检索耗时最长的 Top N 查询语句。

get_blocking_locks(): 查询 pg_locks 和 pg_stat_activity 联合视图，返回当前造成阻塞的会话与锁信息。

explain_query(query: str): 传入一段 SQL，返回数据库的执行计划（底层强制在事务中执行后 ROLLBACK 以防副作用）。

execute_safe_select(query: str): 允许执行自由查询。底层硬编码限制：拦截所有 DML/DDL 关键字，强制 SET TRANSACTION READ ONLY，并在外层强制拼接 LIMIT 100。

执行网关 MCP (Executable Gateway - 仅在 DBA 授权后由系统调用)

create_storage_snapshot(): 触发底层的存储快照，返回 Snapshot ID 作为回滚锚点。

execute_tuning_script(sql_script: str, token: str): 接收 DBA 审批后的修复脚本。验证身份透传 Token 后，在数据库中物理执行。

rollback_to_snapshot(snapshot_id: str): 紧急情况下的快速回退接口。

4 Multi-Agent 拓扑架构 (LangGraph Topology)
系统被设计为一个带监督者的层级网络 (Supervisor with Worker Nodes) `` 拓扑结构：

State (全局状态)：基于 TypedDict，包含：alert_info (告警输入), metrics_data (采集的指标), hypotheses (根因假设列表), tuning_plan (调优脚本), approval_status (DBA审批结果)。

Supervisor Node (总控节点)：接收告警输入，决定状态流转路径。

Diagnostic & RAG Node (诊断节点)：调用读探针 MCP 与 pgvector，向全局状态追加 hypotheses (可能的根因)。

Validation / Critic Node (交叉验证节点)：读取 hypotheses，自主生成并执行 SQL（通过 MCP）去验证假设是否成立，裁剪掉幻觉分支。

Planner Node (规划节点)：将验证后的根因转化为具体的调优 SQL 脚本。

HITL Node (人工审核打断点)：利用 LangGraph 的 interrupt 机制 `` 将状态持久化挂起。等待 DBA 审核完毕（同意/拒绝/修改）后唤醒。

Execution Node (物理执行节点)：仅在审核通过后触发，顺序调用执行网关 MCP 的“打快照”与“应用调优”工具。

5 项目的整体架构层次与职责划分
基础设施与持久化层：提供核心业务数据库实例 (CloudNativePG)、物理快照能力，以及为 Agent 提供上下文记忆 (Checkpointer) 与知识存储 (pgvector)。

安全隔离与工具网关层：作为 Agent 与物理资源的唯一合法通信管道，利用双栈 MCP (读/写隔离) 强制实施权限校验与破坏性指令拦截。

智能体图编排层：运行 LangGraph，控制多智能体 (Supervisor, Diagnostic, Critic, Planner) 的流转逻辑与状态管理，消除单模型上下文切换导致的幻觉。

多模态知识与 RAG 层：提供 Metric-to-Text 转化器、非结构化运维文档解析器，增强 Agent 的推理背景。

交互与人工审核层：提供 Human-in-the-loop (HITL) 交互界面（如 Approval Dashboard），将最终决策权（审批/一键快照回退）交还给人类 DBA。

6 项目的目录结构骨架 (Directory Structure)
db_self_healing_agent/
├── agents/                       # LangGraph 多智能体编排层
│   ├── init.py
│   ├── state.py                  # 定义 LangGraph 的全局 State (TypedDict)
│   ├── supervisor.py             # 路由与总控节点
│   ├── diagnostic_node.py        # 诊断与 RAG 检索节点
│   ├── critic_node.py            # 动态交叉验证节点
│   ├── planner_node.py           # 调优脚本生成节点
│   └── workflow.py               # 构建 StateGraph, 编译 Graph 并配置 checkpointer
├── mcp_servers/                  # MCP Server 实现层
│   ├── read_probe_server.py      # 只读探针 MCP (暴露指标查询, EXPLAIN 工具)
│   ├── write_execute_server.py   # 写执行 MCP (暴露快照、DDL 执行工具)
│   └── security_utils.py         # SQL 注入拦截与事务包裹器
├── rag/                          # 多模态检索增强层
│   ├── document_loader.py        # PostgreSQL 手册与历史工单解析
│   ├── metric_to_text.py         # 将时序指标转化为语义文本
│   └── pgvector_store.py         # pgvector 向量数据库检索逻辑
├── api/                          # 前端与外部交互接口
│   ├── main.py                   # FastAPI 入口 (提供 Webhook 接收告警)
│   └── hitl_routes.py            # 暴露给 DBA 控制台的审核接口 (Approve/Reject)
├── k8s/                          # 云原生部署配置
│   ├── cloudnativepg_cluster.yaml
│   └── snapshot_class.yaml
├──.env                          # 环境变量配置
├── tools_config.json             # MCP 工具的注册与权限配置文件
└── requirements.txt

7 阶段性开发任务 (Phased Development Tasks)
项目落地建议分为 4 个核心 Sprint 进行：

Phase 1: 基础设施与 MCP 网关打底 (Weeks 1-2)

部署测试用 PostgreSQL 实例与 CloudNativePG。

使用 Python MCP SDK 开发 read_probe_server.py，实现 EXPLAIN、pg_locks 等基础只读工具的注册。

Phase 2: RAG 层与知识注入 (Weeks 3-4)

开启 pgvector 扩展，搭建 pgvector_store.py。

实现 Metrics-to-Text 转换逻辑，并将 PostgreSQL 官方排障手册向量化入库。

Phase 3: LangGraph 核心工作流构建 (Weeks 5-6)

基于 StateGraph 串联各节点流转。

重点攻坚 Critic 节点，确保模型能自主生成探测 SQL 并验证自身假设。

实现基于 Checkpointer 的工作流挂起机制 (HITL)。

Phase 4: 执行闭环与安全托底 (Weeks 7-8)

开发 write_execute_server.py，并实现 OAuth 身份透传。

对接 Volume Snapshot API，确保快照执行的原子性。

联调 Web 审核看板，跑通“告警 -> 诊断验证 -> 挂起审核 -> 打快照 -> 修复”的端到端全链路。

