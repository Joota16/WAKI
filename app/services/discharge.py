import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Protocol

from app.config import Settings
from app.integrations.senamhi_discharge import DISCHARGE_STATIONS
from app.repositories.discharge import DischargeRepository
from app.schemas.hydrology import DischargeBatch, DischargeReading, DischargeSnapshot, DischargeStation, RiverId

logger = logging.getLogger(__name__)


class DischargeProvider(Protocol):
    async def fetch(self, station: DischargeStation) -> DischargeBatch: ...


class DischargeService:
    def __init__(self, repository: DischargeRepository, provider: DischargeProvider, settings: Settings):
        self.repository, self.provider, self.settings = repository, provider, settings
        self._sync_lock = asyncio.Lock()

    async def refresh(self):
        async with self._sync_lock:
            for station in DISCHARGE_STATIONS:
                attempted_at = datetime.now(timezone.utc).isoformat()
                try:
                    batch = await self.provider.fetch(station)
                    self.repository.save(station.code, batch, attempted_at, datetime.now(timezone.utc).isoformat())
                except Exception as exc:
                    self.repository.record_error(station.code, attempted_at)
                    logger.warning("No se pudo actualizar el caudal SENAMHI %s: %s", station.code, type(exc).__name__)

    async def run(self):
        while True:
            try:
                await self.refresh()
            except Exception:
                logger.exception("No se pudo guardar la sincronización de caudales.")
            await asyncio.sleep(self.settings.senamhi_poll_seconds)

    def get(self, river_id: RiverId) -> list[DischargeSnapshot]:
        return [self._snapshot(station) for station in DISCHARGE_STATIONS if station.river_id == river_id]

    def _snapshot(self, station: DischargeStation) -> DischargeSnapshot:
        state, rows = self.repository.snapshot(station.code)
        all_readings = [DischargeReading(**row) for row in rows]
        # Ventana de 72 horas respecto a la última fecha publicada, aunque la fuente esté atrasada.
        start = all_readings[-1].observed_at - timedelta(hours=72) if all_readings else None
        readings = [item for item in all_readings if item.observed_at >= start]
        latest = next((item for item in reversed(readings) if item.discharge_m3s is not None), None)
        status, message = "loading", "Esperando la primera consulta a SENAMHI…"
        if latest:
            status, message = "ok", "Dato publicado por SENAMHI, sujeto a revisión."
            if datetime.now(timezone.utc) - latest.observed_at > timedelta(hours=24):
                status, message = "stale", "La última lectura disponible tiene más de 24 horas."
        elif state:
            status, message = "error", "SENAMHI no tiene caudales disponibles en la última consulta."
        source_error = bool(state and state["last_error"])
        if source_error:
            status, message = "error", ("No se pudo actualizar SENAMHI. Se conserva la última lectura guardada."
                                       if latest else "No se pudo consultar SENAMHI. Se reintentará automáticamente.")
        if not self.settings.senamhi_enabled:
            status, message = "disabled", "La actualización automática está desactivada."
        return DischargeSnapshot(
            station=station, status=status, message=message, readings=readings, latest=latest,
            source_url=state["source_url"] if state and state["source_url"] else station.source_url,
            last_attempt_at=state["last_attempt_at"] if state else None,
            last_success_at=state["last_success_at"] if state else None, source_error=source_error,
        )
