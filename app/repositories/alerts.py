import json

from app.db.database import Database


class InvalidAlertSource(ValueError):
    pass


class AlertsRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, values: dict):
        with self.database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if values.get('source_type') == 'report':
                source = db.execute("SELECT review_status FROM reports WHERE id=?", (values['source_id'],)).fetchone()
                if source is None or source['review_status'] != 'validated':
                    raise InvalidAlertSource('El reporte ya no está validado. Actualiza los lugares disponibles.')
            columns = tuple(values)
            db.execute(f"INSERT INTO alerts({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                       tuple(values.values()))
            db.execute("INSERT INTO public_events(event_type,payload_json,created_at) VALUES ('alert_created',?,?)",
                       (json.dumps({'alert_id': values['id']}), values['created_at']))

    def get(self, alert_id: str):
        with self.database.connect() as db:
            row = db.execute('SELECT * FROM alerts WHERE id=?', (alert_id,)).fetchone()
        return dict(row) if row else None

    def close(self, alert_id: str, actor: str, now: str):
        with self.database.connect() as db:
            changed = db.execute('UPDATE alerts SET active=0, closed_at=?, closed_by=? WHERE id=? AND active=1',
                                 (now, actor, alert_id)).rowcount
            if changed:
                db.execute("INSERT INTO public_events(event_type,payload_json,created_at) VALUES ('alert_closed',?,?)",
                           (json.dumps({'alert_id': alert_id}), now))

    def snapshot(self):
        with self.database.connect() as db:
            db.execute('BEGIN')
            rows = db.execute('SELECT * FROM alerts WHERE active=1 ORDER BY created_at DESC,id DESC').fetchall()
            cursor = db.execute('SELECT COALESCE(MAX(sequence),0) FROM public_events').fetchone()[0]
        return [dict(row) for row in rows], cursor

    def events_since(self, after: int):
        with self.database.connect() as db:
            rows = db.execute('SELECT * FROM public_events WHERE sequence>? ORDER BY sequence LIMIT 100', (after,)).fetchall()
        return [dict(row) for row in rows]

    def monitoring_points(self):
        with self.database.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM alert_monitoring_points ORDER BY camera_id')]

    def save_point(self, camera_id: str, values: dict, actor: str, now: str):
        with self.database.connect() as db:
            db.execute('''INSERT INTO alert_monitoring_points(camera_id,name,latitude,longitude,updated_at,updated_by)
                VALUES (?,?,?,?,?,?) ON CONFLICT(camera_id) DO UPDATE SET
                name=excluded.name, latitude=excluded.latitude, longitude=excluded.longitude,
                updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                       (camera_id, values['name'], values['latitude'], values['longitude'], now, actor))

    def source_report(self, report_id: str):
        with self.database.connect() as db:
            row = db.execute("SELECT id,latitude,longitude,reviewed_at FROM reports WHERE id=? AND review_status='validated'",
                             (report_id,)).fetchone()
            return dict(row) if row else None

    def validated_locations(self, limit: int, offset: int):
        with self.database.connect() as db:
            db.execute('BEGIN')
            total = db.execute("SELECT COUNT(*) FROM reports WHERE review_status='validated'").fetchone()[0]
            rows = db.execute('''SELECT id,latitude,longitude,reviewed_at FROM reports WHERE review_status='validated'
                ORDER BY reviewed_at DESC,id DESC LIMIT ? OFFSET ?''', (limit, offset)).fetchall()
            return [dict(row) for row in rows], total

    def history(self, limit: int, offset: int, status: str):
        with self.database.connect() as db:
            db.execute('BEGIN')
            active = {'active': 1, 'closed': 0}.get(status)
            where = '(? IS NULL OR a.active=?)'
            total = db.execute(f'SELECT COUNT(*) FROM alerts a WHERE {where}', (active, active)).fetchone()[0]
            rows = db.execute(f'''SELECT a.*, u.username AS published_by, c.username AS closed_by_name
                FROM alerts a JOIN users u ON u.id=a.created_by LEFT JOIN users c ON c.id=a.closed_by
                WHERE {where} ORDER BY a.created_at DESC,a.id DESC LIMIT ? OFFSET ?''',
                              (active, active, limit, offset)).fetchall()
            return [dict(row) for row in rows], total
