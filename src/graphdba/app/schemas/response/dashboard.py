from pydantic import BaseModel, Field

from graphdba.app.schemas.response.alert import AlertListItem
from graphdba.app.schemas.response.ticket import TicketListItem


class RunStatusCount(BaseModel):
    key: str
    label: str
    count: int


class DashboardStatsResponse(BaseModel):
    active_alerts: int
    active_runs: int
    pending_approval: int
    solved_24h: int
    recent_alerts: list[AlertListItem] = Field(default_factory=list)
    pending_tickets: list[TicketListItem] = Field(default_factory=list)
    run_status_distribution: list[RunStatusCount] = Field(default_factory=list)
