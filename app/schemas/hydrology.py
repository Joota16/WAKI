from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

RiverId = Literal["chillon", "rimac"]
HydrologyStatus = Literal["loading", "ok", "stale", "error", "disabled", "not_configured"]


class HydrologicalStation(BaseModel):
    code: str
    name: str
    river_id: RiverId
    source_url: str


class DailyLevel(BaseModel):
    observed_date: date
    level_m: float | None = Field(default=None, allow_inf_nan=False)


class HydrologySnapshot(BaseModel):
    river_id: RiverId
    station: HydrologicalStation | None = None
    metric: Literal["daily_mean_water_level"] = "daily_mean_water_level"
    unit: Literal["m"] = "m"
    status: HydrologyStatus
    message: str
    readings: list[DailyLevel] = Field(default_factory=list)
    latest: DailyLevel | None = None
    previous_day_change_m: float | None = None
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    source_error: bool = False


class DischargeStation(HydrologicalStation):
    id: Literal["obrajillo", "puente-magdalena"]
    chart_gap_seconds: int


class DischargeThresholds(BaseModel):
    yellow_m3s: float = Field(gt=0, allow_inf_nan=False)
    orange_m3s: float = Field(gt=0, allow_inf_nan=False)
    red_m3s: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def ordered(self):
        if not self.yellow_m3s < self.orange_m3s < self.red_m3s:
            raise ValueError('Los umbrales deben aumentar de amarillo a rojo.')
        return self


class DischargeReading(BaseModel):
    observed_at: datetime  # UTC; la interfaz muestra America/Lima.
    discharge_m3s: float | None = Field(default=None, allow_inf_nan=False, ge=0)
    thresholds: DischargeThresholds | None = None

    @computed_field
    @property
    def threshold_level(self) -> Literal['below_yellow', 'yellow', 'orange', 'red'] | None:
        if self.thresholds is None or self.discharge_m3s is None:
            return None
        for level in ('red', 'orange', 'yellow'):
            if self.discharge_m3s >= getattr(self.thresholds, level + '_m3s'):
                return level
        return 'below_yellow'


class DischargeBatch(BaseModel):
    readings: list[DischargeReading]
    source_url: str


class DischargeSnapshot(BaseModel):
    station: DischargeStation
    metric: Literal["hourly_discharge"] = "hourly_discharge"
    unit: Literal["m3/s"] = "m3/s"
    status: HydrologyStatus
    message: str
    readings: list[DischargeReading] = Field(default_factory=list)
    latest: DischargeReading | None = None
    source_url: str
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    source_error: bool = False
