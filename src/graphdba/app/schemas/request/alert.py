from pydantic import BaseModel, Field

class AlertLabels(BaseModel):
    alertname: str = Field(description="The name of the alert metric")
    instance: str = Field(description="The target database instance host:port")
    severity: str = Field(description="The severity of the alert")

class AlertAnnotations(BaseModel):
    summary: str
    description: str | None = Field(default=None)

class AlertItem(BaseModel):
    """Individual alert within the Alertmanager webhook payload."""
    status: str
    labels: AlertLabels
    annotations: AlertAnnotations
    startsAt: str
    endsAt: str
    generatorURL: str = ""
    fingerprint: str

class AlertRequest(BaseModel):
    """Alertmanager webhook payload format."""
    version: str = "4"
    groupKey: str = ""
    status: str
    receiver: str
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)
    externalURL: str = ""
    truncatedAlerts: int = 0
    alerts: list[AlertItem]