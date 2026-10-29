import asyncio
from datetime import datetime, timezone
import logging
from typing import Protocol
from zoneinfo import ZoneInfo

from app.config import Settings
from app.integrations.senamhi_weather import WEATHER_STATIONS
from app.repositories.weather import WeatherRepository
from app.schemas.hydrology import RiverId
from app.schemas.weather import DailyWeather, WeatherSnapshot, WeatherStation, WeatherValue

logger = logging.getLogger(__name__)


class WeatherProvider(Protocol):
    async def fetch(self, station: WeatherStation) -> list[DailyWeather]: ...


class WeatherService:
    def __init__(self, repository: WeatherRepository, provider: WeatherProvider, settings: Settings):
        self.repository, self.provider, self.settings = repository, provider, settings
        self._sync_lock = asyncio.Lock()

    async def refresh(self):
        async with self._sync_lock:
            for station in WEATHER_STATIONS.values():
                attempted_at = datetime.now(timezone.utc).isoformat()
                try:
                    readings = await self.provider.fetch(station)
                    self.repository.save(station.code, readings, attempted_at, datetime.now(timezone.utc).isoformat())
                except Exception as exc:
                    self.repository.record_error(station.code, attempted_at)
                    logger.warning("No se pudo actualizar la meteorología SENAMHI %s: %s", station.code, type(exc).__name__)

    async def run(self):
        while True:
            try:
                await self.refresh()
            except Exception:
                logger.exception("No se pudo guardar la sincronización meteorológica.")
            await asyncio.sleep(self.settings.senamhi_poll_seconds)

    def get(self, river_id: RiverId) -> WeatherSnapshot:
        station = WEATHER_STATIONS.get(river_id)
        if station is None:
            return WeatherSnapshot(river_id=river_id, status="not_configured",
                                   message="No hay una estación meteorológica conectada para este río.")
        state, rows = self.repository.snapshot(station.code)
        readings = [DailyWeather(**row) for row in rows]

        def latest(key):
            reading = next((item for item in reversed(readings) if getattr(item, key) is not None), None)
            return WeatherValue(observed_date=reading.observed_date, value=getattr(reading, key)) if reading else None

        precipitation, tmax, tmin = (latest(key) for key in ("precipitation_mm", "temperature_max_c", "temperature_min_c"))
        available = [item for item in (precipitation, tmax, tmin) if item is not None]
        status, message = "loading", "Esperando la primera consulta meteorológica a SENAMHI…"
        if available:
            status, message = "ok", "Datos diarios publicados por SENAMHI."
            newest = max(item.observed_date for item in available)
            if (datetime.now(ZoneInfo("America/Lima")).date() - newest).days > 2:
                status, message = "stale", ""
        elif state:
            status, message = "error", "La fuente no contiene lecturas meteorológicas disponibles."
        source_error = bool(state and state["last_error"])
        if source_error:
            status, message = "error", ("No se pudo actualizar SENAMHI. Se conservan las lecturas guardadas y sus fechas."
                                       if available else "No se pudo consultar SENAMHI. Se reintentará automáticamente.")
        if not self.settings.senamhi_enabled:
            status, message = "disabled", "La actualización automática está desactivada."
        return WeatherSnapshot(
            river_id=river_id, station=station, status=status, message=message, readings=readings,
            latest_precipitation=precipitation, latest_temperature_max=tmax, latest_temperature_min=tmin,
            last_attempt_at=state["last_attempt_at"] if state else None,
            last_success_at=state["last_success_at"] if state else None, source_error=source_error,
        )
