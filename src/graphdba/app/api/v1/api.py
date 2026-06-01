from fastapi import APIRouter
from graphdba.app.api.v1.endpoints import runs
from graphdba.app.api.v1.endpoints import alerts
from graphdba.app.api.v1.endpoints import login
from graphdba.app.api.v1.endpoints import me
from graphdba.app.api.v1.endpoints import stream_run
from graphdba.app.api.v1.endpoints import approve_run

api_router = APIRouter()

api_router.include_router(
    alerts.router,
    prefix="/alerts",
    tags=["Alerts"]
)

api_router.include_router(
    login.router,
    prefix="/login",
    tags=["Login"]
)

api_router.include_router(
    me.router,
    tags=["Login"]
)

api_router.include_router(
    runs.router,
    prefix="/runs",
    tags=["Get the current agent's state in current thread"]
)

api_router.include_router(
    stream_run.router,
    prefix="/runs",
    tags=["Stream agent node events for a run"]
)

api_router.include_router(
    approve_run.router,
    prefix="/runs",
    tags=["Update agent state for approval"]
)
