import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager

from graphdba.app.api.v1.api import api_router
from graphdba.agents.runtime import AgentRuntime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent_runtime = AgentRuntime()
    logger.info("Agent runtime manager registered")
    try:
        yield
    finally:
        await app.state.agent_runtime.close()
        logger.info("FastAPI application shutdown completed")

## TODO: use PostgreSQL saver
app = FastAPI(title="GraphDBA", lifespan=lifespan)
app.include_router(api_router, prefix="/api/v1")
