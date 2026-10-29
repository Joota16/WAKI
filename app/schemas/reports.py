from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Situation = Literal[
    "Desborde de agua hacia pistas o casas",
    "El agua está carcomiendo la orilla",
    "Basura, troncos o rocas atorados en el puente",
    "Ruidos fuertes de piedras o amenaza de huaico",
    "Casas, muros o postes en peligro de caer",
    "Personas o animales atrapados en el cauce",
]


class ReportInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    river_section: Literal["Río Chillón", "Río Rímac"]
    district: str = Field(min_length=1, max_length=120)
    reference: str = Field(min_length=1, max_length=300)
    observations: str = Field(default="", max_length=2000)
    observed_condition: Literal["critico", "muy-alto", "alto", "normal"]
    situations: list[Situation] = Field(default_factory=list, max_length=6)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    accuracy_m: float | None = Field(default=None, gt=0, le=20_000_000, allow_inf_nan=False)
    anonymous: bool = False
    contact_name: str = Field(default="", max_length=80)
    contact_phone: str = Field(default="", max_length=30, pattern=r"^[+0-9 ()-]*$")
    neighborhood: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def validate_location_and_privacy(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitud y longitud deben enviarse juntas.")
        if self.accuracy_m is not None and self.latitude is None:
            raise ValueError("La precisión de ubicación requiere coordenadas.")
        self.situations = list(dict.fromkeys(self.situations))
        if self.anonymous:
            self.contact_name = self.contact_phone = self.neighborhood = ""
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
    river_section: str
    district: str
    reference: str
    observations: str
    observed_condition: str
    situations: list[str]
    latitude: float | None
    longitude: float | None
    accuracy_m: float | None
    anonymous: bool
    photos: list[PhotoOut]
    analysis_status: Literal["not_configured"] = "not_configured"
    detail_url: str


class ReportPage(BaseModel):
    items: list[ReportOut]
    total: int
    limit: int
    offset: int

