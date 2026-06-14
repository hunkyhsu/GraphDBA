import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI

from graphdba.app.api.v1.api import api_router
from graphdba.app.services.recovery import recover_active_alerts
from graphdba.agents.container import AgentContainer
from graphdba.config.settings import get_settings
from graphdba.database.repositories import alerts
from graphdba.database.session import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

async def run_startup_recovery(app: FastAPI) -> None:
    try:
        async with AsyncSessionLocal() as session:
            recoverable_alerts = await alerts.list_recoverable_alerts(session)
        if not recoverable_alerts:
            logger.info("Startup recovery skipped; no recoverable alerts found")
            return

        graph = await app.state.agent_container.get_graph()
        await recover_active_alerts(graph)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Startup recovery failed")

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent_container = AgentContainer()
    if get_settings().agent.startup_recovery_enabled:
        app.state.recovery_task = asyncio.create_task(run_startup_recovery(app))
    else:
        app.state.recovery_task = None
        logger.info("Startup recovery disabled")
    logger.info("Agent container registered")
    try:
        yield
    finally:
        if app.state.recovery_task is not None:
            app.state.recovery_task.cancel()
            with suppress(asyncio.CancelledError):
                await app.state.recovery_task
        await app.state.agent_container.close()
        logger.info("FastAPI application shutdown completed")

## TODO: use PostgreSQL saver
app = FastAPI(title="GraphDBA", lifespan=lifespan)
app.include_router(api_router, prefix="/api/v1")
