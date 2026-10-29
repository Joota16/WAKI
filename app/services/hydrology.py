import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Protocol
from zoneinfo import ZoneInfo

from app.config import Settings
from app.integrations.senamhi import STATIONS
from app.repositories.hydrology import HydrologyRepository
from app.schemas.hydrology import DailyLevel, HydrologicalStation, HydrologySnapshot, RiverId

logger = logging.getLogger(__name__)


class LevelsProvider(Protocol):
    async def fetch(self, station: HydrologicalStation) -> list[DailyLevel]: ...


class HydrologyService:
    def __init__(self, repository: HydrologyRepository, provider: LevelsProvider, settings: Settings):
        self.repository, self.provider, self.settings = repository, provider, settings
        self._sync_lock = asyncio.Lock()

    async def refresh(self):
        async with self._sync_lock:
            for station in STATIONS.values():
                attempted_at = datetime.now(timezone.utc).isoformat()
                try:
                    readings = await self.provider.fetch(station)
                    self.repository.save(station.code, readings, attempted_at, datetime.now(timezone.utc).isoformat())
                except Exception as exc:
                    # Se conserva la última serie válida; el siguiente ciclo reintenta.
                    self.repository.record_error(station.code, attempted_at)
                    logger.warning("No se pudo actualizar SENAMHI, estación %s: %s", station.code, type(exc).__name__)

    async def run(self):
        while True:
            try:
                await self.refresh()
            except Exception:
                logger.exception("No se pudo guardar el estado de sincronización de niveles.")
            await asyncio.sleep(self.settings.senamhi_poll_seconds)

    def get(self, river_id: RiverId) -> HydrologySnapshot:
        station = STATIONS.get(river_id)
        if station is None:
            return HydrologySnapshot(river_id=river_id, status="not_configured",
                                     message="Todavía no hay una estación conectada para este río.")
        state, rows = self.repository.snapshot(station.code)
        readings = [DailyLevel(**row) for row in rows]
        latest = next((item for item in reversed(readings) if item.level_m is not None), None)
        change = None
        if latest:
            previous = next((item for item in readings if item.observed_date == latest.observed_date - timedelta(days=1)), None)
            if previous and previous.level_m is not None:
                change = round(latest.level_m - previous.level_m, 3)
        source_error = bool(state and state["last_error"])
        status, message = "loading", "Esperando la primera consulta a SENAMHI…"
        if latest:
            status, message = "ok", "Promedio diario publicado por SENAMHI."
            age = datetime.now(ZoneInfo("America/Lima")).date() - latest.observed_date
            if age.days > 2:
                status, message = "stale", "El último promedio disponible tiene más de dos días."
        elif state:
            status, message = "error", "SENAMHI no tiene niveles disponibles en la última consulta."
        if source_error:
            status, message = "error", ("No se pudo actualizar SENAMHI. Se conserva la última lectura guardada."
                                        if latest else "No se pudo consultar SENAMHI. Se reintentará automáticamente.")
        if not self.settings.senamhi_enabled:
            status, message = "disabled", "La actualización automática está desactivada."
        return HydrologySnapshot(
            river_id=river_id, station=station, status=status, message=message,
            readings=readings, latest=latest, previous_day_change_m=change, source_error=source_error,
            last_attempt_at=state["last_attempt_at"] if state else None,
            last_success_at=state["last_success_at"] if state else None,
        )
