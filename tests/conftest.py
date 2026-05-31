from __future__ import annotations
import yaml
from typing import Any
from mcp.types import Tool, ListToolsResult

_READ_TOOLS = {"get_blocking_locks", "execute_safe_select", "get_pg_stat_statements", "explain_query"}
_WRITE_TOOLS = {
    "create_alert",
    "get_alert",
    "update_alert_status",
    "propose_ticket",
    "approve_ticket",
    "execute_ticket",
}


class ManagedMockClient:
    """Async context manager replacing the real MCP ClientSession for testing.

    Loads tool responses from a YAML fixture. list_tools() derives its tool
    list from the fixture's mock_responses keys, filtered by mode, so the LLM
    only sees tools that have a configured response.
    """

    def __init__(self, fixture_path: str, mode: str) -> None:
        self.fixture_path = fixture_path
        self.mode = mode  # "read" or "write"
        self._fixture: dict = {}

    async def __aenter__(self) -> ManagedMockClient:
        with open(self.fixture_path) as f:
            self._fixture = yaml.safe_load(f)
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def list_tools(self) -> ListToolsResult:
        mock_responses: dict = self._fixture.get("mock_responses", {})
        allowed = _READ_TOOLS if self.mode == "read" else _WRITE_TOOLS
        tools = [
            Tool(
                name=name,
                description=self._fixture.get("tool_descriptions", {}).get(
                    name, f"Mock {self.mode} tool: {name}"
                ),
                inputSchema={"type": "object", "properties": {}},
            )
            for name in mock_responses
            if name in allowed
        ]
        return ListToolsResult(tools=tools)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        mock_responses: dict = self._fixture.get("mock_responses", {})
        if name in mock_responses:
            return str(mock_responses[name]["data"])
        return f"[mock] no response configured for tool '{name}'"

    @staticmethod
    def load_alert_payload(fixture_path: str) -> dict:
        with open(fixture_path) as f:
            fixture = yaml.safe_load(f)
        return fixture.get("alert_payload", {})

    @staticmethod
    def get_alert_payload() -> dict:
        return ManagedMockClient.load_alert_payload("tests/data/deadlock_sample.yaml")
