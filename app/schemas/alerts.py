from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class AlertInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: Literal['inundacion', 'derrumbe', 'huaico', 'otro']
    title: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=5, max_length=2000)
    location: str = Field(min_length=2, max_length=200)


class AlertOut(AlertInput):
    id: UUID
    created_at: AwareDatetime
    active: bool
    closed_at: AwareDatetime | None


class AlertsSnapshot(BaseModel):
    items: list[AlertOut]
    cursor: int
