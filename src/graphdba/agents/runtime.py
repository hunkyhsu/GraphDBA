from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING

from graphdba.agents.graph import build_graph
from graphdba.config.dependencies import (
    get_chat_llm,
    get_embedding,
    get_mcp_client,
    get_reasoning_llm,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from mcp.client.session import ClientSession

logger = logging.getLogger(__name__)


class AgentRuntime:
    """Lazy owner for graph dependencies that are expensive to initialize."""

    def __init__(self) -> None:
        self._exit_stack: AsyncExitStack | None = None
        self._graph: CompiledStateGraph | None = None
        self._mcp_read: ClientSession | None = None
        self._mcp_write: ClientSession | None = None
        self._init_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._graph is not None:
            return

        async with self._init_lock:
            if self._graph is not None:
                return

            logger.info("Initializing agent runtime...")
            exit_stack = AsyncExitStack()
            try:
                mcp_read = await exit_stack.enter_async_context(get_mcp_client(is_read=True))
                mcp_write = await exit_stack.enter_async_context(get_mcp_client(is_read=False))
                graph = build_graph(
                    llm_reasoning=get_reasoning_llm(),
                    llm_chat=get_chat_llm(),
                    embedding=get_embedding(),
                    mcp_read_client=mcp_read,
                    mcp_write_client=mcp_write,
                )
            except Exception:
                await exit_stack.aclose()
                logger.exception("Agent runtime initialization failed")
                raise

            self._exit_stack = exit_stack
            self._mcp_read = mcp_read
            self._mcp_write = mcp_write
            self._graph = graph
            logger.info("Agent runtime initialized")

    async def get_graph(self) -> CompiledStateGraph:
        await self.initialize()
        if self._graph is None:
            raise RuntimeError("Agent runtime graph is not initialized")
        return self._graph

    async def get_mcp_read(self) -> ClientSession:
        await self.initialize()
        if self._mcp_read is None:
            raise RuntimeError("Agent runtime read MCP client is not initialized")
        return self._mcp_read

    async def get_mcp_write(self) -> ClientSession:
        await self.initialize()
        if self._mcp_write is None:
            raise RuntimeError("Agent runtime write MCP client is not initialized")
        return self._mcp_write

    async def close(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        self._exit_stack = None
        self._mcp_read = None
        self._mcp_write = None
        self._graph = None
        logger.info("Agent runtime closed")
