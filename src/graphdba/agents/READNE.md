# Multi-Agent Diagnosis-Validation Structure
> Author: Hunky Hsu
> Created at: 2026-05-06

```diagram
graph TD
    A[Event Trigger] --> B{Orchestrator Node}
    B -- fatal --> F[Exit: Alert Human DBA]
    B -- non-fatal --> C[Diagnostic Node]
    C --> D[Validation Node]
    D -- confirmed --> E[Planning Node]
    D -- retry --> G[Retry Controller]
    G -- retry --> C
    G -- max retries exceeded --> F
    
    subgraph Planning & Execution
        E --> H[Human Approval Gate]
        H -- approve --> I[Execution & Rollback Node]
        H -- reject --> J[Exit: Ticket Rejected]
        I --> K[Post-Execution Verification]
    end
```

## Alert
Exceptions in Database are recorded by 3 layers:
1. Database Kernel Record
   1. Error Logs: record the critical system crashes, permission denials, or SQL syntax errors. 
   Example: `026-05-06 03:00:00 UTC [1234] ERROR: deadlock detected ...`
   2. Statistics Collector: `pg_stat_activity` and `pg_stat_statements`
   3. Slow Query Logs: when a SQL executes over `log_min_duration_statement`, the system would record.
2. Autonomous Monitoring Tools: 
   1. Prometheus + Postgres Exporter: convert the data in `pg_stat` into time-series metrics
   2. AWS CloudWatch: graphical alarms
3. Alert Management System: When Prometheus detects exceptions, it sends a JSON to alert manager.

The Prometheus Alertmanager's Sturcture is the standard. This is where message send to DBA without agent. And this is also where message send to agent as `AlertPayload`:
```json
{
  "receiver": "db-agent-webhook",
  "status": "firing", 
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "PostgresHighCpuUsage",
        "severity": "critical",
        "instance": "192.168.1.10:5432",
        "cluster": "prod-customer-db",
        "job": "postgres_exporter"
      },
      "annotations": {
        "summary": "Database instance CPU usage is high",
        "description": "CPU usage on 192.168.1.10 is 95% (threshold 90%)",
        "suggestion": "Check pg_stat_activity for long running queries."
      },
      "startsAt": "2026-05-06T03:00:00Z",
      "fingerprint": "a1b2c3d4e5f6"
    }
  ],
  "commonLabels": {
    "cluster": "prod-customer-db"
  },
  "externalURL": "http://alertmanager.example.com"
}
```

**Orchestrator Node**:
if the alert=FATAL, then exit the whole strcuture and alert the Human DBA
if the alert=NO_FATAL, then go to Diagnostic Node
In No fatal alert, if high-freq jitter, then consolidate the alerts and exit

**Diagnostic & Validation Node**:
Diagnostic Node diagnostic alert without MCP tools

多重异常并发：Diagnostic节点可能因信息不足无法抉择，Validation可能发现多个原因都部分成立，系统需要具备综合多原因生成修复计划的能力。

权限与认证失效：数据库中Agent使用的诊断账号权限不足、密码过期；或Write MCP Server用于生成工单的JWT Token在异步流程中意外失效。

部分失效（Partial Failure）：Execution节点成功执行了SQL却无法更新工单状态为SUCCESS，导致状态不一致。工具调用也可能因网络抖动返回不完整数据，而LLM难以判断其有效性。

高频抖动（Flapping Alert）：同一个异常在短时间内反复触发、恢复。状态机需具备防抖动逻辑，在Orchestrator处合并或丢弃短时间内的重复告警。

上下文窗口溢出：在多轮Diagnostic-Validation循环中，所有工具调用返回的指标数据和思考过程会塞满LLM上下文，导致后续节点性能下降甚至调用失败。

Orchestrator Node (分流与防抖)：增强分流能力，判断fatal，监控非致命异常是否在高频抖动，若是则合并告警直接退出。

Diagnostic & Validation (动态循环与熔断)：Retry Controller不仅控制重试，还需实现结构性熔断机制（如循环超过3次或提示词注入检测阈值直接熔断退出）；当多原因都成立时，应允许传递多个有效假设进入Planning。此外，Retry Controller还应作为全局循环管理器，若从Validation返回重试，会携带上一轮的精简摘要给Diagnostic，防止上下文无限膨胀。

Planning & Execution (计划、审批与恢复)：Planning统一接收假设生成修复计划并提交审核。Human Approval Gate设计为同步阻塞节点，将Agent暂停（可利用LangGraph的interrupt机制），完全由人类DBA决定继续、修改或拒绝。Execution节点执行成功后，需进入Post-Execution Verification节点再次调用Read MCP相关指标验证修复效果，形成价值闭环。

Shared State (共享状态)：建议将task_id、alert_raw、diagnosis_list、validated_hypotheses、attempt_count、human_approval、final_plan等字段作为强类型Schema，而非自由文本传递，防止Agent间信息丢失。

全局安全护栏（Pre/Post-Tool Use Guards）
任务前（Pre-Tool Use）：在Planning调用Write MCP前，基于关键词拦截DROP DATABASE等高危操作，防止这类请求进入工单系统。

任务后（Post-Tool Use）：每次Execution节点执行写操作后，强制记录不可变审计日志（谁批准、执行了什么SQL、是否成功）。

防幻觉熔断：监控Diagnostic节点是否有逻辑死循环，或Validation是否反复调用相同工具无进展。

此外，还有一项关键的架构增强建议：若能将Diagnostic改进为并行执行，同时开启多个独立的“思考链”去推测锁、IO等不同原因，再由Validation并行验证，可显著提升诊断速度和准确性。同时，所有节点都应向可观测性平台（如LangSmith）上报详细决策日志、Token消耗等信息。


总结：

如果（诊断 LLM 生成的工具调用一直出错）或者（假设一直出错）或者（不生成合法的输出）或者（明明已经提示不要生成已验证失败的假设/工具调用，但是还是重复生成一样的），那会都会统一记录重试次数加一，超过最大重试次数直接断开。

conditions:
- Finished 正常诊断-验证
- 诊断 LLM 生成工具调用出错
  - 工具名称或参数错误 validation
  - 正常工具调用但是验证失败 validation
- 诊断 LLM 生成假设根因出错 validation
- 诊断 LLM 生成重复输出
- Finished 诊断 LLM 过度自信没有输出工具调用或假设
- Finished 诊断 LLM 觉得没有合适工具 / 觉得问题太复杂
- Finished 断电、网络超时、API 宕机
- Finished 诊断 LLM 由于 token 限制或者其他原因输出不完整或乱码