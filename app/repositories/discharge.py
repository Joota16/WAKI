from app.db.database import Database
from app.schemas.hydrology import DischargeBatch


class DischargeRepository:
    def __init__(self, database: Database):
        self.database = database

    def save(self, station_code: str, batch: DischargeBatch, attempted_at: str, completed_at: str):
        with self.database.connect() as connection:
            connection.executemany("""
                INSERT INTO discharge_readings(station_code, observed_at, discharge_m3s) VALUES (?, ?, ?)
                ON CONFLICT(station_code, observed_at) DO UPDATE SET discharge_m3s=excluded.discharge_m3s
            """, [(station_code, item.observed_at.isoformat(), item.discharge_m3s) for item in batch.readings])
            connection.execute("""
                INSERT INTO discharge_sync(station_code, source_url, last_attempt_at, last_success_at, last_error)
                VALUES (?, ?, ?, ?, NULL) ON CONFLICT(station_code) DO UPDATE SET source_url=excluded.source_url,
                last_attempt_at=excluded.last_attempt_at, last_success_at=excluded.last_success_at, last_error=NULL
            """, (station_code, batch.source_url, attempted_at, completed_at))

    def record_error(self, station_code: str, attempted_at: str):
        with self.database.connect() as connection:
            connection.execute("""
                INSERT INTO discharge_sync(station_code, last_attempt_at, last_error) VALUES (?, ?, 'source_unavailable')
                ON CONFLICT(station_code) DO UPDATE SET
                last_attempt_at=excluded.last_attempt_at, last_error=excluded.last_error
            """, (station_code, attempted_at))

    def snapshot(self, station_code: str):
        with self.database.connect() as connection:
            connection.execute("BEGIN")
            state = connection.execute("SELECT * FROM discharge_sync WHERE station_code=?", (station_code,)).fetchone()
            rows = connection.execute("""
                SELECT observed_at, discharge_m3s FROM discharge_readings WHERE station_code=?
                ORDER BY observed_at DESC LIMIT 2000
            """, (station_code,)).fetchall()
        return dict(state) if state else None, [dict(row) for row in reversed(rows)]
