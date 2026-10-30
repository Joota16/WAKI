from datetime import datetime, timezone
import json
from uuid import uuid4

from app.repositories.alerts import AlertsRepository
from app.schemas.alerts import AlertInput, AlertOut, AlertsSnapshot


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

    def create(self, values: AlertInput, actor_id: str):
        alert_id = str(uuid4())
        self.repository.create({**values.model_dump(), 'id': alert_id, 'created_by': actor_id,
                                'created_at': datetime.now(timezone.utc).isoformat()})
        return self.get(alert_id)

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
