from pydantic import BaseModel, Field

class AlertItem(BaseModel):
    """Individual alert within the Alertmanager webhook payload."""
    status: str
    labels: dict[str, str]
    annotations: dict[str, str]
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