from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.attention import AttentionLevel

Situation = Literal[
    "Desborde de agua hacia pistas o casas",
    "El agua está carcomiendo la orilla",
    "Basura, troncos o rocas atorados en el puente",
    "Ruidos fuertes de piedras o amenaza de huaico",
    "Casas, muros o postes en peligro de caer",
    "Personas o animales atrapados en el cauce",
]
ReviewStatus = Literal['pending', 'validated', 'discarded']
REVIEW_LABELS = {'pending': 'Pendiente de verificación', 'validated': 'Validado por la administración', 'discarded': 'Descartado'}


class ReportReview(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    decision: ReviewStatus
    notes: str = Field(default='', max_length=1000)
    expected_version: int = Field(ge=0)
    attention_level: AttentionLevel | None = None

    @model_validator(mode='after')
    def validate_attention(self):
        if self.decision == 'validated':
            if self.attention_level is None:
                raise ValueError('Selecciona el nivel de atención al validar el reporte.')
            if not self.notes:
                raise ValueError('Indica la justificación de la evaluación.')
        elif self.attention_level is not None:
            raise ValueError('Solo un reporte validado puede asignar un nivel de atención.')
        return self


class ReportInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    observations: str = Field(default="", max_length=2000)
    observed_condition: Literal["critico", "muy-alto", "alto", "normal"]
    situations: list[Situation] = Field(default_factory=list, max_length=6)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    accuracy_m: float | None = Field(default=None, gt=0, le=20_000_000, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_location(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitud y longitud deben enviarse juntas.")
        if self.accuracy_m is not None and self.latitude is None:
            raise ValueError("La precisión de ubicación requiere coordenadas.")
        self.situations = list(dict.fromkeys(self.situations))
        return self


class PhotoOut(BaseModel):
    id: str
    width: int
    height: int
    size_bytes: int
    url: str


class ReportOut(BaseModel):
    id: str
    created_at: datetime
    observations: str
    observed_condition: str
    situations: list[str]
    latitude: float | None
    longitude: float | None
    accuracy_m: float | None
    photos: list[PhotoOut]
    analysis_status: Literal["not_configured"] = "not_configured"
    detail_url: str
    review_status: ReviewStatus = 'pending'
    review_label: str = 'Pendiente de verificación'
    review_version: int = 0
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    attention_level: AttentionLevel | None = None
    attention_label: str | None = None


class ReportPage(BaseModel):
    items: list[ReportOut]
    total: int
    limit: int
    offset: int

