from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

AlertKind = Literal['inundacion', 'derrumbe', 'erosion_fluvial']
HistoricalAlertKind = Literal['inundacion', 'derrumbe', 'erosion_fluvial', 'huaico', 'otro']
MessageKey = Literal['stay_clear', 'avoid_travel', 'official_updates']


class AlertInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: AlertKind
    title: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=5, max_length=2000)
    location: str = Field(min_length=2, max_length=200)


class AlertOut(AlertInput):
    kind: HistoricalAlertKind
    id: UUID
    created_at: AwareDatetime
    active: bool
    closed_at: AwareDatetime | None
    source_type: Literal['camera', 'report'] | None = None
    source_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    message_key: MessageKey | None = None
    radius_m: int | None = Field(default=None, ge=1, le=10000)


class GuidedAlertInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: AlertKind
    source_type: Literal['camera', 'report']
    source_id: str = Field(min_length=1, max_length=64)
    message_key: MessageKey
    radius_m: int = Field(default=30, ge=1, le=10000)


class MonitoringPointInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=3, max_length=120)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class AlertHistoryItem(AlertOut):
    published_by: str
    closed_by: str | None = None


class AlertHistoryPage(BaseModel):
    items: list[AlertHistoryItem]
    total: int
    limit: int
    offset: int


class AlertsSnapshot(BaseModel):
    items: list[AlertOut]
    cursor: int
