from datetime import datetime, timezone
import logging
from uuid import UUID

from app.config import Settings
from app.repositories.cameras import CamerasRepository
from app.schemas.cameras import CameraDefinition, CameraFrame, CameraUpload, LatestCameraFrame
from app.services.images import ImagesService
from app.services.processing import ProcessingService

logger = logging.getLogger(__name__)
CAMERAS = {
    item.id: item for item in (
        CameraDefinition(id="chillon-01", name="Cámara del río Chillón", river_id="chillon"),
        CameraDefinition(id="rimac-01", name="Cámara del río Rímac", river_id="rimac"),
    )
}

# Ubicación de instalación indicada por el equipo: mismo punto de Malecón Chillón
# que utiliza el mapa de estaciones (static/js/dashboard/stations-data.js).
DEFAULT_CAMERA_LOCATIONS = {
    'chillon-01': {
        'name': 'Malecón Chillón',
        'latitude': -11.913546150295304,
        'longitude': -77.07124450899127,
    },
}


class CameraNotFound(LookupError):
    pass


class CameraFrameNotFound(LookupError):
    pass


class CamerasService:
    def __init__(self, repository: CamerasRepository, images: ImagesService, settings: Settings,
                 processing: ProcessingService | None = None):
        self.repository, self.images, self.settings = repository, images, settings
        self.processing = processing

    def camera(self, camera_id: str) -> CameraDefinition:
        if camera_id not in CAMERAS:
            raise CameraNotFound("La cámara no está registrada.")
        return CAMERAS[camera_id]

    def initialize(self):
        self.images.initialize()
        referenced = self.repository.filenames()
        for path in self.images.directory.glob("*.jpg"):
            if path.name not in referenced:
                path.unlink(missing_ok=True)

    @staticmethod
    def frame(row: dict) -> CameraFrame:
        return CameraFrame(**row, image_url=f"/api/cameras/{row['camera_id']}/frames/{UUID(row['id'])}/image")

    def receive(self, metadata: CameraUpload, content: bytes) -> CameraFrame:
        self.camera(metadata.camera_id)
        photo = self.images.store(content)
        values = {**photo, "camera_id": metadata.camera_id, "received_at": datetime.now(timezone.utc).isoformat(),
                  "captured_at": metadata.captured_at.isoformat() if metadata.captured_at else None}
        try:
            normalized = self.images.path(photo).read_bytes() if self.processing else None
            expired = self.repository.add(values, self.settings.iot_retention_images)
        except Exception:
            self.images.delete(photo)
            raise
        if self.processing:
            try:
                self.processing.enqueue(values, self.camera(metadata.camera_id).river_id, normalized)
            except Exception:
                logger.exception('No se pudo registrar el análisis de la captura %s', photo['id'])
        for row in expired:
            try:
                self.images.delete(row)
            except OSError:
                logger.warning("No se pudo eliminar una captura IoT vencida: %s", row["id"])
        return self.frame(values)

    def latest(self, camera_id: str) -> LatestCameraFrame:
        camera = self.camera(camera_id)
        row = self.repository.latest(camera_id)
        return LatestCameraFrame(camera=camera, latest=self.frame(row) if row else None,
                                 server_time=datetime.now(timezone.utc))

    def image(self, camera_id: str, frame_id: UUID) -> bytes:
        self.camera(camera_id)
        row = self.repository.get(camera_id, frame_id.hex)
        if not row:
            raise CameraFrameNotFound("La captura no existe o ya venció su retención.")
        try:
            return self.images.path(row).read_bytes()
        except FileNotFoundError as exc:
            raise CameraFrameNotFound("El archivo de la captura no está disponible.") from exc
