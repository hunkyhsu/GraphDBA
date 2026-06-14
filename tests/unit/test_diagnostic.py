import pytest
import json
from unittest.mock import MagicMock, AsyncMock
from asyncio import TimeoutError
from pydantic import ValidationError
from langchain_core.exceptions import OutputParserException

# 假设你的文件名为 diagnostic.py
from graphdba.agents.diagnostic import DiagnosticNode, DiagnosticOutput

# 引入你最新的状态定义
from graphdba.agents.state import (
    AlertPayload, Hypothesis, ValidationAction, 
    AgentWorkflowStatus, HypothesisStatus
)

# ==========================================
# Fixtures: 构造全局 Mock 对象
# ==========================================
@pytest.fixture
def mock_mcp_client():
    """Mock MCP 客户端，默认返回一个可用工具"""
    client = AsyncMock()
    mock_tool = MagicMock()
    mock_tool.name = "pg_stat_activity"
    mock_tool.description = "Get current PG activities"
    mock_tool.inputSchema = {"type": "object"}
    
    # 模拟 mcp.types.ListToolsResult
    mock_result = MagicMock()
    mock_result.tools = [mock_tool]
    client.list_tools.return_value = mock_result
    return client

@pytest.fixture
def mock_llm():
    """Mock LangChain LLM"""
    llm = MagicMock()
    llm.with_structured_output.return_value = MagicMock()
    return llm

@pytest.fixture
def mock_embeddings():
    """Mock Embeddings 模型"""
    embeddings = AsyncMock()
    # 默认返回两个正交向量 (相似度为 0)
    embeddings.aembed_documents.return_value = [[1.0, 0.0], [0.0, 1.0]]
    return embeddings

@pytest.fixture
def base_state():
    """基础的 LangGraph State，严格匹配最新的 AlertPayload 及其 alias"""
    return {
        "alert": {
            "fingerprint": "alert-12345",        # alias for id
            "alertname": "High CPU",             # alias for name
            "instance": "192.168.1.100:5432",    # new required field
            "severity": "critical",
            "status": "firing",                  # new required field
            "summary": "CPU usage is extremely high", # new required field
            "description": "CPU > 90%",
            "startsAt": "2026-05-12T10:00:00Z",  # alias for starts_at
            "raw_payload": {"cpu": 95}
        },
        "attempt_count": 0,
        "rejected_hypotheses": []
    }

# ==========================================
# Helper: 快速创建合法的 Hypothesis 实例
# ==========================================
def create_mock_hypothesis(id: str, root_cause: str, tool_name: str, status: HypothesisStatus = HypothesisStatus.PENDING) -> Hypothesis:
    """辅助函数：填充必填字段以通过 Pydantic 校验"""
    return Hypothesis(
        id=id,
        root_cause=root_cause,
        description=["Detailed description of the issue"],
        confidence_score=0.95,
        validation_actions=[ValidationAction(tool_name=tool_name, tool_payload={})],
        expected_result="Expected to see high lock wait time",
        status=status,
        feedback=None
    )


# ==========================================
# Category 1: 静态结构层 (Pydantic 校验器)
# ==========================================
class TestDiagnosticOutput:
    def test_valid_escalation(self):
        """Case 1.1: 合法人工升级"""
        output = DiagnosticOutput(
            require_human_escalation=True,
            escalation_reason="Query is too obfuscated, need human.",
            hypotheses=None
        )
        assert output.require_human_escalation is True

    def test_invalid_escalation(self):
        """Case 1.2: 非法人工升级（无理由）"""
        with pytest.raises(ValueError, match="Escalation reason must be provided"):
            DiagnosticOutput(require_human_escalation=True, escalation_reason=None)

    def test_valid_hypotheses(self):
        """Case 1.3: 合法假设生成"""
        hypo = create_mock_hypothesis("test", "Bad index", "tool_a")
        output = DiagnosticOutput(
            require_human_escalation=False,
            hypotheses=[hypo]
        )
        assert len(output.hypotheses) == 1

    def test_missing_validation_actions(self):
        """Case 1.5: 假设缺少验证动作"""
        hypo_invalid = Hypothesis(
            id="test", 
            root_cause="Bad index", 
            description=["Detail"], 
            confidence_score=0.8, 
            expected_result="Expect result",
            status=HypothesisStatus.PENDING,
            validation_actions=[] # 这里为空，应触发校验
        )
        with pytest.raises(ValueError, match="is missing validation actions"):
            DiagnosticOutput(require_human_escalation=False, hypotheses=[hypo_invalid])


# ==========================================
# Category 2: 外部依赖层 (MCP & LLM 边界)
# ==========================================
@pytest.mark.asyncio
class TestDiagnosticNodeExternal:
    @pytest.mark.asyncio
    async def test_mcp_empty_tools(self, mock_llm, mock_mcp_client, mock_embeddings, base_state):
        """Case 2.1: MCP 工具列表为空短路"""
        mock_mcp_client.list_tools.return_value.tools = []
        node = DiagnosticNode(mock_llm, mock_mcp_client, mock_embeddings)
        
        result = await node(base_state)
        assert result["workflow_status"] == AgentWorkflowStatus.FAILED.value
        assert "No tools found" in result["failed_reason"]
        mock_llm.with_structured_output().ainvoke.assert_not_called()
    @pytest.mark.asyncio
    async def test_llm_retry_success(self, mock_llm, mock_mcp_client, mock_embeddings, base_state):
        """Case 2.2: LLM 单次解析失败但重试成功"""
        hypo = create_mock_hypothesis("test", "Test Issue", "tool")
        valid_output = DiagnosticOutput(require_human_escalation=False, hypotheses=[hypo])
        
        node = DiagnosticNode(mock_llm, mock_mcp_client, mock_embeddings)
        
        mock_chain = AsyncMock()
        mock_chain.ainvoke.side_effect = [
            OutputParserException("Invalid JSON"),
            valid_output
        ]
        
        node.prompt = MagicMock()
        node.prompt.__or__.return_value = mock_chain
        
        result = await node(base_state)
        
        assert result["workflow_status"] == AgentWorkflowStatus.DIAGNOSED.value
        assert mock_chain.ainvoke.call_count == 2 
    @pytest.mark.asyncio
    async def test_llm_max_retries_exhausted(self, mock_llm, mock_mcp_client, mock_embeddings, base_state):
        """Case 2.3: LLM 持续崩溃耗尽重试"""
        node = DiagnosticNode(mock_llm, mock_mcp_client, mock_embeddings)
        
        mock_chain = AsyncMock()
        mock_chain.ainvoke.side_effect = TimeoutError("LLM Hung")
        node.prompt = MagicMock()
        node.prompt.__or__.return_value = mock_chain
        
        result = await node(base_state)
        
        assert result["workflow_status"] == AgentWorkflowStatus.FAILED.value
        assert "max retry count" in result["failed_reason"]
        assert mock_chain.ainvoke.call_count == node.MAX_RETRY


# ==========================================
# Category 3: 核心业务层 (假设去重机制 Deduplication)
# ==========================================
@pytest.mark.asyncio
class TestDiagnosticNodeDeduplication:
    @pytest.mark.asyncio
    async def _setup_node_with_output(self, mock_llm, mock_mcp, mock_emb, output_hypotheses):
        """辅助方法：配置 Node 并设置 LLM 固定的输出"""
        node = DiagnosticNode(mock_llm, mock_mcp, mock_emb)
        output = DiagnosticOutput(require_human_escalation=False, hypotheses=output_hypotheses)
        
        # 同样使用拦截机制
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = output
        node.prompt = MagicMock()
        node.prompt.__or__.return_value = mock_chain
        
        return node
    @pytest.mark.asyncio
    async def test_inter_batch_dedup_rejected(self, mock_llm, mock_mcp_client, mock_embeddings, base_state):
        """Case 3.1: 命中 REJECTED，应当过滤"""
        mock_embeddings.aembed_documents.return_value = [[1.0, 0.0], [1.0, 0.0]] 
        
        old_hypo = create_mock_hypothesis("old", "Locks", "tool_A", HypothesisStatus.REJECTED)
        base_state["rejected_hypotheses"] = [old_hypo.model_dump()]
        
        new_hypo = create_mock_hypothesis("new", "Locks", "tool_A", HypothesisStatus.PENDING)
        
        node = await self._setup_node_with_output(mock_llm, mock_mcp_client, mock_embeddings, [new_hypo])
        result = await node(base_state)
        
        assert result["workflow_status"] == AgentWorkflowStatus.FAILED.value
        assert "filtered" in result["failed_reason"]
    @pytest.mark.asyncio
    async def test_inter_batch_dedup_inconclusive_diff_tools(self, mock_llm, mock_mcp_client, mock_embeddings, base_state):
        """Case 3.2: 命中 INCONCLUSIVE 但工具不同，应当保留"""
        mock_embeddings.aembed_documents.return_value = [[1.0, 0.0], [1.0, 0.0]] 
        
        old_hypo = create_mock_hypothesis("old", "Locks", "tool_A", HypothesisStatus.INCONCLUSIVE)
        base_state["rejected_hypotheses"] = [old_hypo.model_dump()]
        
        # 注意：工具换成了 tool_B
        new_hypo = create_mock_hypothesis("new", "Locks", "tool_B", HypothesisStatus.PENDING)
        
        node = await self._setup_node_with_output(mock_llm, mock_mcp_client, mock_embeddings, [new_hypo])
        result = await node(base_state)
        
        assert result["workflow_status"] == AgentWorkflowStatus.DIAGNOSED.value
        assert len(result["current_hypotheses"]) == 1
    @pytest.mark.asyncio
    async def test_intra_batch_dedup(self, mock_llm, mock_mcp_client, mock_embeddings, base_state):
        """Case 3.4: 批次内去重"""
        h1 = create_mock_hypothesis("1", "CPU spikes due to index", "t1")
        h2 = create_mock_hypothesis("2", "Missing index causing CPU load", "t1")
        
        node = await self._setup_node_with_output(mock_llm, mock_mcp_client, mock_embeddings, [h1, h2])
        # 强制 _are_semantically_similar 在做 intra-batch 比较时返回 True
        node._are_semantically_similar = AsyncMock(return_value=True) 
        
        result = await node(base_state)
        
        assert result["workflow_status"] == AgentWorkflowStatus.DIAGNOSED.value
        assert len(result["current_hypotheses"]) == 1


# ==========================================
# Category 4: 极端系统异常 (System Exceptions)
# ==========================================
@pytest.mark.asyncio
class TestDiagnosticNodeExceptions:
    @pytest.mark.asyncio
    async def test_embedding_timeout(self, mock_llm, mock_mcp_client, mock_embeddings, base_state):
        """Case 4.1: Embedding 接口超时导致的大异常捕获"""
        h1 = create_mock_hypothesis("1", "Test", "t1")
        node = DiagnosticNode(mock_llm, mock_mcp_client, mock_embeddings)
        
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = DiagnosticOutput(require_human_escalation=False, hypotheses=[h1])
        node.prompt = MagicMock()
        node.prompt.__or__.return_value = mock_chain
        
        mock_embeddings.aembed_documents.side_effect = TimeoutError("Vector DB Down")
        base_state["rejected_hypotheses"] = [h1.model_dump()]
        
        result = await node(base_state)
        
        assert result["workflow_status"] == AgentWorkflowStatus.FAILED.value
        assert "Critical diagnostic node failure: TimeoutError" in result["failed_reason"]
    @pytest.mark.asyncio
    async def test_no_embedding_model(self, mock_llm, mock_mcp_client, base_state):
        """Case 4.2: 无 Embedding 模型初始化"""
        h1 = create_mock_hypothesis("1", "Test", "t1")
        node = DiagnosticNode(mock_llm, mock_mcp_client, embeddings=None)
        
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = DiagnosticOutput(require_human_escalation=False, hypotheses=[h1])
        node.prompt = MagicMock()
        node.prompt.__or__.return_value = mock_chain
        
        base_state["rejected_hypotheses"] = [h1.model_dump()]
        
        result = await node(base_state)
        
        assert result["workflow_status"] == AgentWorkflowStatus.FAILED.value
        assert "Critical diagnostic node failure: RuntimeError" in result["failed_reason"]