from fastapi import APIRouter
from graphdba.app.api.v1 import alerts
from graphdba.app.api.v1 import approve_run
from graphdba.app.api.v1 import dashboard
from graphdba.app.api.v1 import login
from graphdba.app.api.v1 import me
from graphdba.app.api.v1 import runs
from graphdba.app.api.v1 import stream_run
from graphdba.app.api.v1 import tickets

api_router = APIRouter()

api_router.include_router(
    alerts.router,
    prefix="/alerts",
    tags=["Alerts"]
)

api_router.include_router(
    dashboard.router,
    prefix="/dashboard",
    tags=["Dashboard"]
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
    tickets.router,
    prefix="/tickets",
    tags=["Tickets"]
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
