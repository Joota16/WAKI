from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from uuid import uuid4

from app.config import Settings
from app.repositories.reports import ReportsRepository
from app.schemas.reports import ReportInput, ReportOut, ReportPage
from app.services.images import ImagesService, InvalidImage


class ReportNotFound(LookupError):
    pass


class DuplicateRequest(ValueError):
    pass


class ReportsService:
    def __init__(self, repository: ReportsRepository, images: ImagesService, settings: Settings):
        self.repository = repository
        self.images = images
        self.settings = settings

    @staticmethod
    def present(row: dict) -> ReportOut:
        # Lista explícita: los contactos y datos internos nunca salen en la API pública.
        fields = {name: row[name] for name in (
            "id", "created_at", "river_section", "district", "reference", "observations",
            "observed_condition", "situations", "latitude", "longitude", "accuracy_m", "anonymous",
        )}
        fields["photos"] = [
            {**{key: photo[key] for key in ("id", "width", "height", "size_bytes")},
             "url": f"/api/reports/{row['id']}/photos/{photo['id']}"}
            for photo in row["photos"]
        ]
        return ReportOut(**fields, detail_url=f"/reportes/{row['id']}")

    def create(self, metadata: ReportInput, contents: list[bytes], request_key: str | None) -> ReportOut:
        if not 1 <= len(contents) <= self.settings.max_photos:
            raise InvalidImage(f"Adjunta entre 1 y {self.settings.max_photos} fotografías.")
        payload = metadata.model_dump()
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode())
        for content in contents:
            digest.update(hashlib.sha256(content).digest())
        fingerprint = digest.hexdigest()

        def previous_report():
            previous = self.repository.get_by_key(request_key) if request_key else None
            if previous and previous["fingerprint"] != fingerprint:
                raise DuplicateRequest("Este intento ya guardó otro contenido. Inicia un nuevo reporte.")
            return self.present(previous) if previous else None

        previous = previous_report()
        if previous:
            return previous
        row = {"id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
               "request_key": request_key, "fingerprint": fingerprint, **payload}
        row["situations_json"] = json.dumps(row.pop("situations"), ensure_ascii=False)
        photos = []
        try:
            for content in contents:
                photos.append(self.images.store(content))
            self.repository.create(row, photos)
        except Exception as exc:
            for photo in photos:
                self.images.delete(photo)
            if isinstance(exc, sqlite3.IntegrityError):
                previous = previous_report()
                if previous:
                    return previous
            raise
        return self.get(row["id"])

    def get(self, report_id: str) -> ReportOut:
        row = self.repository.get(report_id)
        if row is None:
            raise ReportNotFound("No se encontró el reporte.")
        return self.present(row)

    def list(self, limit: int, offset: int) -> ReportPage:
        rows, total = self.repository.list(limit, offset)
        return ReportPage(items=[self.present(row) for row in rows], total=total, limit=limit, offset=offset)

    def photo_path(self, report_id: str, photo_id: str):
        photo = self.repository.get_photo(report_id, photo_id)
        if photo is None or not self.images.path(photo).is_file():
            raise ReportNotFound("No se encontró la fotografía.")
        return self.images.path(photo)

