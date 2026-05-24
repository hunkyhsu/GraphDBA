import os
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager, AsyncExitStack

from graphdba.app.api.v1.api import api_router
from graphdba.agents.graph import build_graph
from graphdba.database.connection_pool import get_db_pool
from graphdba.database.init import init_database_schema
from graphdba.config.dependencies import get_reasoning_llm, get_chat_llm, get_mcp_client, get_embedding

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
# Run: uv run uvicorn graphdba.app.app:app --reload --port 8000
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        logger.info("FastAPI application start up starting...")
        # 3 connection pool here
        # init the connection pool and database schema
        pool = await stack.enter_async_context(get_db_pool())
        app.state.pool = pool
        await init_database_schema(pool)
        # init the W/R MCP
        mcp_read = await stack.enter_async_context(get_mcp_client(is_read=True))
        mcp_write = await stack.enter_async_context(get_mcp_client(is_read=False))
        # init agent graph
        graph = build_graph(
            llm_reasoning=get_reasoning_llm(),
            llm_chat=get_chat_llm(),
            embedding=get_embedding(),
            mcp_read_client=mcp_read,
            mcp_write_client=mcp_write,
        )
        app.state.graph = graph
        app.state.mcp_read = mcp_read
        app.state.mcp_write = mcp_write

        logger.info("FastAPI application startup completed")
        yield
        logger.info("FastAPI application shutdown completed")

## TODO: use PostgreSQL saver
app = FastAPI(title="GraphDBA", lifespan=lifespan)
app.include_router(api_router, prefix="/api/v1")