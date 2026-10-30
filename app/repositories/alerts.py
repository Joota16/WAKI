import json

from app.db.database import Database


class AlertsRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, values: dict):
        with self.database.connect() as db:
            db.execute('''INSERT INTO alerts(id,kind,title,message,location,created_at,created_by)
                VALUES (:id,:kind,:title,:message,:location,:created_at,:created_by)''', values)
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
