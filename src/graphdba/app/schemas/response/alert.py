from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

class AlertsStateResponse(BaseModel):
    status: str
    run_ids: list[str]


class AlertListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    alert_id: UUID = Field(validation_alias="id")
    alertname: str = Field(validation_alias="name")
    severity: str
    status: str
    instance: str | None = None
    cluster_name: str | None = None
    database_name: str | None = None
    database_role: str | None = None
    started_at: datetime | None = None
    updated_at: datetime


class AlertListResponse(BaseModel):
    items: list[AlertListItem]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class AlertStatsResponse(BaseModel):
    active: int
    critical: int
    pending_review: int
    resolved_24h: int


class AlertDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    alert_id: UUID = Field(validation_alias="id")
    fingerprint: str
    alertname: str = Field(validation_alias="name")
    severity: str
    status: str
    instance: str | None = None
    cluster_name: str | None = None
    database_name: str | None = None
    database_role: str | None = None
    host: str | None = None
    port: int | None = None
    environment: str | None = None
    region: str | None = None
    alert_summary: str = Field(validation_alias="summary")
    description: str | None = None
    labels: dict[str, Any] = Field(default_factory=dict)
    annotations: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    generator_url: str | None = None
    started_at: datetime | None = None
    ends_at: datetime | None = None
    received_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None = None
    resolved_at: datetime | None = None
    occurrence_count: int
    thread_id: str | None = None
    escalation_reason: str | None = None
    failure_reason: str | None = None
