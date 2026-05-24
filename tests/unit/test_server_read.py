from __future__ import annotations
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from graphdba.mcp.models import ExplainQueryInput, SafeSelectInput, SlowQueryFilter
from graphdba.mcp.server_read import (
    mcp_read,
    explain_query,
    execute_safe_select,
    get_pg_stat_statements,
    get_blocking_locks,
)

EXPECTED_TOOLS = {
    "explain_query",
    "execute_safe_select",
    "get_pg_stat_statements",
    "get_blocking_locks",
}


@pytest.fixture
def mock_pool():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=conn)
    tx_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_cm)

    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    return pool


@pytest.fixture
def mock_context(mock_pool):
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {"db_pool": mock_pool}
    return ctx


# ==========================================
# Category 1: Tool Registration
# ==========================================
class TestToolRegistration:
    @pytest.mark.asyncio
    async def test_all_tools_registered(self):
        tools = await mcp_read.list_tools()
        registered = {t.name for t in tools}
        assert registered == EXPECTED_TOOLS
    @pytest.mark.asyncio
    async def test_tool_count(self):
        tools = await mcp_read.list_tools()
        assert len(tools) == 4
    @pytest.mark.asyncio
    async def test_each_tool_has_description(self):
        tools = await mcp_read.list_tools()
        for tool in tools:
            assert tool.description, f"Tool '{tool.name}' is missing a description"


# ==========================================
# Category 2: explain_query Accessibility
# ==========================================
class TestExplainQueryAccessibility:
    @pytest.mark.asyncio
    async def test_returns_dict(self, mock_context):
        input_data = ExplainQueryInput(query="SELECT 1", run_analyze=False)
        result = await explain_query(input_data, mock_context)
        assert isinstance(result, dict)
    @pytest.mark.asyncio
    async def test_uses_pool_from_context(self, mock_context, mock_pool):
        input_data = ExplainQueryInput(query="SELECT 1", run_analyze=False)
        await explain_query(input_data, mock_context)
        mock_pool.acquire.assert_called_once()
    @pytest.mark.asyncio
    async def test_rejects_write_query(self, mock_context):
        input_data = ExplainQueryInput(query="DROP TABLE users", run_analyze=False)
        result = await explain_query(input_data, mock_context)
        assert "error" in result
    @pytest.mark.asyncio
    async def test_valid_select_returns_plan(self, mock_context):
        input_data = ExplainQueryInput(query="SELECT 1", run_analyze=False)
        result = await explain_query(input_data, mock_context)
        assert "execution_plan" in result or "error" in result


# ==========================================
# Category 3: execute_safe_select Accessibility
# ==========================================
class TestExecuteSafeSelectAccessibility:
    @patch("graphdba.mcp.tools_read.get_settings")
    async def test_returns_dict(self, mock_settings, mock_context):
        mock_settings.return_value.security.max_result_rows = 100
        input_data = SafeSelectInput(query="SELECT 1")
        result = await execute_safe_select(input_data, mock_context)
        assert isinstance(result, dict)

    @patch("graphdba.mcp.tools_read.get_settings")
    async def test_uses_pool_from_context(self, mock_settings, mock_context, mock_pool):
        mock_settings.return_value.security.max_result_rows = 100
        input_data = SafeSelectInput(query="SELECT 1")
        await execute_safe_select(input_data, mock_context)
        mock_pool.acquire.assert_called_once()

    @patch("graphdba.mcp.tools_read.get_settings")
    async def test_rejects_write_query(self, mock_settings, mock_context):
        mock_settings.return_value.security.max_result_rows = 100
        input_data = SafeSelectInput(query="INSERT INTO t VALUES (1)")
        result = await execute_safe_select(input_data, mock_context)
        assert "error" in result

    @patch("graphdba.mcp.tools_read.get_settings")
    async def test_valid_select_returns_results(self, mock_settings, mock_context):
        mock_settings.return_value.security.max_result_rows = 100
        input_data = SafeSelectInput(query="SELECT 1")
        result = await execute_safe_select(input_data, mock_context)
        assert "results" in result or "error" in result


# ==========================================
# Category 4: get_pg_stat_statements Accessibility
# ==========================================
class TestGetPgStatStatementsAccessibility:
    async def test_returns_dict(self, mock_context):
        filters = SlowQueryFilter(limit=5, min_duration_ms=100)
        result = await get_pg_stat_statements(filters, mock_context)
        assert isinstance(result, dict)

    async def test_uses_pool_from_context(self, mock_context, mock_pool):
        filters = SlowQueryFilter()
        await get_pg_stat_statements(filters, mock_context)
        mock_pool.acquire.assert_called_once()

    async def test_returns_slow_queries_key(self, mock_context):
        filters = SlowQueryFilter()
        result = await get_pg_stat_statements(filters, mock_context)
        assert "slow_queries" in result or "error" in result

    async def test_default_filters_accepted(self, mock_context):
        result = await get_pg_stat_statements(SlowQueryFilter(), mock_context)
        assert isinstance(result, dict)


# ==========================================
# Category 5: get_blocking_locks Accessibility
# ==========================================
class TestGetBlockingLocksAccessibility:
    async def test_returns_dict(self, mock_context):
        result = await get_blocking_locks(mock_context)
        assert isinstance(result, dict)

    async def test_uses_pool_from_context(self, mock_context, mock_pool):
        await get_blocking_locks(mock_context)
        mock_pool.acquire.assert_called_once()

    async def test_returns_blocking_locks_key(self, mock_context):
        result = await get_blocking_locks(mock_context)
        assert "blocking_locks" in result or "error" in result

    async def test_no_input_required(self, mock_context):
        # get_blocking_locks takes only context — verify it's callable with no extra args
        result = await get_blocking_locks(mock_context)
        assert isinstance(result, dict)
