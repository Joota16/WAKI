from datetime import datetime, timezone
import json
from math import asin, cos, radians, sin, sqrt
from uuid import UUID, uuid4

from app.repositories.alerts import AlertsRepository, InvalidAlertSource
from app.schemas.alerts import AlertHistoryItem, AlertHistoryPage, AlertInput, AlertOut, AlertsSnapshot, GuidedAlertInput
from app.services.cameras import CAMERAS, DEFAULT_CAMERA_LOCATIONS

KIND_LABELS = {'inundacion': 'Inundación', 'derrumbe': 'Derrumbe', 'erosion_fluvial': 'Erosión fluvial'}
# Indicaciones generales: INDECI, recomendaciones ante lluvias intensas y peligros asociados.
# https://www.gob.pe/institucion/indeci/noticias/838989
MESSAGE_OPTIONS = [
    {'id': 'stay_clear', 'label': 'Mantenerse alejado del lugar',
     'text': 'Mantente alejado del área afectada y sigue las indicaciones de las autoridades.'},
    {'id': 'avoid_travel', 'label': 'Evitar circular por el sector',
     'text': 'Evita transitar por el sector afectado y sigue las indicaciones de las autoridades.'},
    {'id': 'official_updates', 'label': 'Mantenerse atento a los avisos',
     'text': 'Mantente informado por los canales oficiales y sigue las indicaciones de las autoridades.'},
]


class AlertNotFound(LookupError):
    pass


class AlertsService:
    def __init__(self, repository: AlertsRepository):
        self.repository = repository

    @staticmethod
    def present(row):
        return AlertOut(**{name: row[name] for name in AlertOut.model_fields})

    def get(self, alert_id: str):
        row = self.repository.get(alert_id)
        if row is None:
            raise AlertNotFound('No se encontró el aviso.')
        return self.present(row)

    def create(self, values: AlertInput | GuidedAlertInput, actor_id: str):
        alert_id = str(uuid4())
        if isinstance(values, GuidedAlertInput):
            source = self.resolve_source(values.source_type, values.source_id)
            template = next(option['text'] for option in MESSAGE_OPTIONS if option['id'] == values.message_key)
            record = {**values.model_dump(), 'source_id': source['source_id'],
                      'title': KIND_LABELS[values.kind], 'location': source['location'],
                      'message': template,
                      'latitude': source['latitude'], 'longitude': source['longitude']}
        else:
            record = values.model_dump()
        self.repository.create({**record, 'id': alert_id, 'created_by': actor_id,
                                'created_at': datetime.now(timezone.utc).isoformat()})
        return self.get(alert_id)

    def camera_sources(self):
        points = {**DEFAULT_CAMERA_LOCATIONS,
                  **{point['camera_id']: point for point in self.repository.monitoring_points()}}
        return [{'source_type': 'camera', 'source_id': camera.id, 'name': points.get(camera.id, {}).get('name', camera.name),
                 'location': points.get(camera.id, {}).get('name', camera.name), 'camera_name': camera.name,
                 'latitude': points.get(camera.id, {}).get('latitude'),
                 'longitude': points.get(camera.id, {}).get('longitude'), 'configured': camera.id in points}
                for camera in CAMERAS.values()]

    @staticmethod
    def report_source(row, cameras):
        location = f"Ubicación del reporte validado {row['id'][:8]}"
        if row['latitude'] is not None:
            nearby = []
            lat = radians(row['latitude'])
            for camera in cameras:
                if not camera['configured']:
                    continue
                dlat = radians(camera['latitude'] - row['latitude'])
                dlon = radians(camera['longitude'] - row['longitude'])
                a = sin(dlat / 2) ** 2 + cos(lat) * cos(radians(camera['latitude'])) * sin(dlon / 2) ** 2
                distance = 6_371_000 * 2 * asin(sqrt(min(1, a)))
                if distance <= 2000:
                    nearby.append((distance, camera['name']))
            if nearby:
                location = f"Cerca de {min(nearby)[1]} (reporte {row['id'][:8]})"
        return {'source_type': 'report', 'source_id': row['id'], 'name': f"Reporte validado {row['id'][:8]}",
                'location': location, 'latitude': row['latitude'], 'longitude': row['longitude'],
                'reviewed_at': row['reviewed_at'], 'configured': row['latitude'] is not None}

    def options(self, limit: int, offset: int):
        cameras = [source for source in self.camera_sources() if CAMERAS[source['source_id']].river_id == 'chillon']
        reports, total = self.repository.validated_locations(limit, offset)
        return {'cameras': cameras, 'reports': [self.report_source(row, cameras) for row in reports],
                'total_reports': total, 'limit': limit, 'offset': offset,
                'kinds': [{'id': key, 'label': label} for key, label in KIND_LABELS.items()],
                'messages': MESSAGE_OPTIONS}

    def resolve_source(self, source_type: str, source_id: str):
        cameras = self.camera_sources()
        if source_type == 'camera':
            source = next((item for item in cameras if item['source_id'] == source_id), None)
        else:
            try:
                source_id = str(UUID(source_id))
            except ValueError as exc:
                raise InvalidAlertSource('Selecciona un reporte validado disponible.') from exc
            report = self.repository.source_report(source_id)
            source = self.report_source(report, cameras) if report else None
        if source is None:
            raise InvalidAlertSource('El lugar seleccionado ya no está disponible. Actualiza los lugares.')
        if not source['configured']:
            raise InvalidAlertSource('Este lugar aún no tiene ubicación. Registra la ubicación de la cámara o selecciona otro reporte.')
        return source

    def save_point(self, camera_id: str, values, actor_id: str):
        if camera_id not in CAMERAS:
            raise InvalidAlertSource('La cámara no está registrada.')
        self.repository.save_point(camera_id, values.model_dump(), actor_id, datetime.now(timezone.utc).isoformat())
        return self.resolve_source('camera', camera_id)

    def history(self, limit: int, offset: int, status: str):
        rows, total = self.repository.history(limit, offset, status)
        return AlertHistoryPage(items=[AlertHistoryItem(**self.present(row).model_dump(),
                                                       published_by=row['published_by'], closed_by=row['closed_by_name'])
                                       for row in rows], total=total, limit=limit, offset=offset)

    def close(self, alert_id: str, actor_id: str):
        self.get(alert_id)
        self.repository.close(alert_id, actor_id, datetime.now(timezone.utc).isoformat())
        return self.get(alert_id)

    def snapshot(self):
        rows, cursor = self.repository.snapshot()
        return AlertsSnapshot(items=[self.present(row) for row in rows], cursor=cursor)

    def events(self, after: int):
        output = []
        for row in self.repository.events_since(after):
            payload = json.loads(row['payload_json'])
            if row['event_type'] in ('alert_created', 'alert_closed'):
                payload = self.get(payload['alert_id']).model_dump(mode='json')
            output.append({'id': row['sequence'], 'type': row['event_type'], 'data': payload})
        return output
