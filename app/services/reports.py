from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from uuid import uuid4

from app.config import Settings
from app.repositories.reports import ReportsRepository
from app.schemas.reports import ReportInput, ReportOut, ReportPage, ReportReview, REVIEW_LABELS
from app.schemas.attention import ATTENTION_LABELS
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
    def present(row: dict, admin=False) -> ReportOut:
        # Solo se publican los campos del contrato de reportes.
        fields = {name: row[name] for name in (
            "id", "created_at", "observations",
            "observed_condition", "situations", "other_situation", "latitude", "longitude", "accuracy_m",
        )}
        fields["photos"] = [
            {**{key: photo[key] for key in ("id", "width", "height", "size_bytes")},
             "url": f"/api/reports/{row['id']}/photos/{photo['id']}"}
            for photo in row["photos"]
        ]
        fields.update(review_status=row['review_status'], review_label=REVIEW_LABELS[row['review_status']],
                      review_version=row['review_version'], reviewed_at=row['reviewed_at'],
                      review_notes=row['review_notes'] if admin else None)
        fields['phone'] = row['phone'] if admin else None
        level = row['attention_level'] if row['review_status'] == 'validated' else None
        fields.update(attention_level=level, attention_label=ATTENTION_LABELS.get(level))
        return ReportOut(**fields, detail_url=f"/reportes/{row['id']}")

    def create(self, metadata: ReportInput, contents: list[bytes], request_key: str | None) -> ReportOut:
        if not 1 <= len(contents) <= self.settings.max_photos:
            raise InvalidImage(f"Adjunta entre 1 y {self.settings.max_photos} fotografías.")
        payload = metadata.model_dump()
        fingerprint_payload = dict(payload)
        if not fingerprint_payload['other_situation']:
            # Conserva la huella de reintentos enviados antes de añadir el campo opcional.
            fingerprint_payload.pop('other_situation')
        if not fingerprint_payload['phone']:
            fingerprint_payload.pop('phone')
        digest = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True).encode())
        for content in contents:
            digest.update(hashlib.sha256(content).digest())
        fingerprint = digest.hexdigest()

        def previous_report():
            previous = self.repository.get_by_key(request_key) if request_key else None
            if previous and previous['review_status'] == 'discarded':
                raise DuplicateRequest('El reporte asociado a ese envío ya no está disponible. Inicia un nuevo reporte.')
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
        # El envío devuelve su comprobante; las consultas públicas requieren validación.
        return self.present(self.repository.get(row["id"], include_discarded=True))

    def get(self, report_id: str, admin=False) -> ReportOut:
        row = self.repository.get(report_id, include_discarded=admin)
        if row is None:
            raise ReportNotFound("No se encontró el reporte.")
        return self.present(row, admin=admin)

    def list(self, limit: int, offset: int, *, admin=False, include_discarded=False, review_status=None) -> ReportPage:
        rows, total = self.repository.list(limit, offset, include_discarded=admin and include_discarded,
                                           review_status=review_status, admin=admin)
        return ReportPage(items=[self.present(row, admin=admin) for row in rows], total=total, limit=limit, offset=offset)

    def photo_path(self, report_id: str, photo_id: str, admin=False):
        photo = self.repository.get_photo(report_id, photo_id, include_discarded=admin)
        if photo is None or not self.images.path(photo).is_file():
            raise ReportNotFound("No se encontró la fotografía.")
        return self.images.path(photo)

    def review(self, report_id: str, values: ReportReview, actor_id: str):
        self.get(report_id, admin=True)
        if not self.repository.review(report_id, actor_id, values.decision, values.notes, values.expected_version,
                                      datetime.now(timezone.utc).isoformat(), values.attention_level):
            raise DuplicateRequest('Otro administrador cambió este reporte. Actualiza antes de revisarlo.')
        return self.get(report_id, admin=True)

