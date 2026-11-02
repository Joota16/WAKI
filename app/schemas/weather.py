from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.hydrology import HydrologicalStation, HydrologyStatus, RiverId


class WeatherStation(HydrologicalStation):
    catalog_code: str


class DailyWeather(BaseModel):
    observed_date: date
    precipitation_mm: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    temperature_max_c: float | None = Field(default=None, allow_inf_nan=False)
    temperature_min_c: float | None = Field(default=None, allow_inf_nan=False)


class WeatherValue(BaseModel):
    observed_date: date
    value: float


class WeatherSnapshot(BaseModel):
    river_id: RiverId
    station: WeatherStation | None = None
    status: HydrologyStatus
    message: str
    precipitation_unit: Literal["mm/day"] = "mm/day"
    temperature_unit: Literal["degC"] = "degC"
    readings: list[DailyWeather] = Field(default_factory=list)
    latest_precipitation: WeatherValue | None = None
    latest_temperature_max: WeatherValue | None = None
    latest_temperature_min: WeatherValue | None = None
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    source_error: bool = False
