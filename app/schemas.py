from pydantic import BaseModel


class DeviceStatus(BaseModel):
    id: int
    name: str
    host: str
    enabled: bool
    is_up: bool | None
    last_latency_ms: float | None
    last_checked: str | None
    last_change: str | None
    uptime_24h: float | None


class GroupStatus(BaseModel):
    id: int
    name: str
    description: str
    devices: list[DeviceStatus]
    total: int
    online: int
    offline: int


class StatusResponse(BaseModel):
    groups: list[GroupStatus]
    ungrouped: list[DeviceStatus]
    total: int
    online: int
    offline: int
    generated_at: str
