from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.database import Database


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class AnalysesRepository:
    def __init__(self, database: Database):
        self.database = database

    def interrupt_pending(self):
        with self.database.connect() as connection:
            connection.execute("""UPDATE image_analyses SET status='error', completed_at=?,
                message='El servidor se reinició antes de terminar. Requiere reintento.'
                WHERE status IN ('queued', 'processing')""", (utcnow(),))

    def add(self, values: dict, max_pending: int, retention: int) -> list[str]:
        with self.database.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            pending = connection.execute("SELECT COUNT(*) FROM image_analyses WHERE status IN ('queued','processing')").fetchone()[0]
            if values['status'] == 'queued' and pending >= max_pending:
                values.update(status='error', message='Cola de IA llena. Captura conservada; requiere reintento.')
            connection.execute("""INSERT INTO image_analyses
                (id, camera_id, river_id, source, received_at, captured_at, created_at, status, message)
                VALUES (:id, :camera_id, :river_id, :source, :received_at, :captured_at, :created_at, :status, :message)""", values)
            expired = [row[0] for row in connection.execute("""SELECT id FROM image_analyses
                WHERE camera_id=? AND status NOT IN ('queued','processing')
                ORDER BY sequence DESC LIMIT -1 OFFSET ?""", (values['camera_id'], retention))]
            connection.executemany('DELETE FROM image_analyses WHERE id=?', [(item,) for item in expired])
        return expired

    def get(self, analysis_id: str):
        with self.database.connect() as connection:
            row = connection.execute('SELECT * FROM image_analyses WHERE id=?', (analysis_id,)).fetchone()
        return dict(row) if row else None

    def list(self, camera_id: str, limit: int, offset: int):
        with self.database.connect() as connection:
            total = connection.execute('SELECT COUNT(*) FROM image_analyses WHERE camera_id=?', (camera_id,)).fetchone()[0]
            rows = connection.execute('SELECT * FROM image_analyses WHERE camera_id=? ORDER BY sequence DESC LIMIT ? OFFSET ?',
                                      (camera_id, limit, offset)).fetchall()
        return [dict(row) for row in rows], total

    def claim(self, analysis_id: str) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute("UPDATE image_analyses SET status='processing', message='' WHERE id=? AND status='queued'", (analysis_id,))
            return cursor.rowcount == 1

    def finish(self, analysis_id: str, status: str, message: str, result: dict | None = None, artifacts: dict | None = None):
        with self.database.connect() as connection:
            connection.execute("""UPDATE image_analyses SET status=?, message=?, completed_at=?, result_json=?, artifacts_json=?
                WHERE id=?""", (status, message, utcnow(), json.dumps(result, ensure_ascii=False, allow_nan=False) if result else None,
                               json.dumps(artifacts or {}), analysis_id))

    def retry(self, analysis_id: str, max_pending: int, status: str, message: str) -> bool:
        with self.database.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            pending = connection.execute("SELECT COUNT(*) FROM image_analyses WHERE status IN ('queued','processing')").fetchone()[0]
            if status == 'queued' and pending >= max_pending:
                return False
            cursor = connection.execute("""UPDATE image_analyses SET status=?, message=?, completed_at=NULL,
                result_json=NULL, artifacts_json='{}' WHERE id=? AND status IN ('error','not_configured','partial')""",
                                        (status, message, analysis_id))
            return cursor.rowcount == 1

    def ids(self) -> set[str]:
        with self.database.connect() as connection:
            return {row[0] for row in connection.execute('SELECT id FROM image_analyses')}

    def prune(self, camera_id: str, retention: int) -> list[str]:
        with self.database.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            expired = [row[0] for row in connection.execute("""SELECT id FROM image_analyses
                WHERE camera_id=? AND status NOT IN ('queued','processing')
                ORDER BY sequence DESC LIMIT -1 OFFSET ?""", (camera_id, retention))]
            connection.executemany('DELETE FROM image_analyses WHERE id=?', [(item,) for item in expired])
        return expired
