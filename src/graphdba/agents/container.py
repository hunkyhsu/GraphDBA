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
from graphdba.config.settings import get_settings
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from mcp.client.session import ClientSession

logger = logging.getLogger(__name__)


class AgentContainer:
    """Lazy owner for graph dependencies that are expensive to initialize."""

    def __init__(self) -> None:
        self._exit_stack: AsyncExitStack | None = None
        self._graph: CompiledStateGraph | None = None
        self._mcp_read: ClientSession | None = None
        self._checkpoint_pool: AsyncConnectionPool | None = None
        self._checkpointer: AsyncPostgresSaver | None = None
        self._init_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._graph is not None:
            return

        async with self._init_lock:
            if self._graph is not None:
                return

            logger.info("Initializing agent container...")
            exit_stack = AsyncExitStack()
            checkpoint_pool: AsyncConnectionPool | None = None
            try:
                database = get_settings().database
                checkpoint_pool = AsyncConnectionPool(
                    conninfo=database.psycopg_connection_string,
                    max_size=database.pool_size,
                    kwargs={
                        "autocommit": True,
                        "prepare_threshold": 0,
                    },
                    open=False,
                )
                await checkpoint_pool.open()
                checkpointer = AsyncPostgresSaver(checkpoint_pool)
                await checkpointer.setup()

                mcp_read = await exit_stack.enter_async_context(get_mcp_client(is_read=True))
                graph = build_graph(
                    llm_reasoning=get_reasoning_llm(),
                    llm_chat=get_chat_llm(),
                    embedding=get_embedding(),
                    mcp_read_client=mcp_read,
                    checkpointer=checkpointer,
                )
            except Exception:
                if checkpoint_pool is not None:
                    await checkpoint_pool.close()
                await exit_stack.aclose()
                logger.exception("Agent container initialization failed")
                raise

            self._exit_stack = exit_stack
            self._mcp_read = mcp_read
            self._checkpoint_pool = checkpoint_pool
            self._checkpointer = checkpointer
            self._graph = graph
            logger.info("Agent container initialized")

    async def get_graph(self) -> CompiledStateGraph:
        await self.initialize()
        if self._graph is None:
            raise RuntimeError("Agent container graph is not initialized")
        return self._graph

    async def get_mcp_read(self) -> ClientSession:
        await self.initialize()
        if self._mcp_read is None:
            raise RuntimeError("Agent container read MCP client is not initialized")
        return self._mcp_read

    async def close(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        if self._checkpoint_pool is not None:
            await self._checkpoint_pool.close()
        self._exit_stack = None
        self._mcp_read = None
        self._checkpoint_pool = None
        self._checkpointer = None
        self._graph = None
        logger.info("Agent container closed")
