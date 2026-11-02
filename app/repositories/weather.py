from app.db.database import Database
from app.schemas.weather import DailyWeather


class WeatherRepository:
    def __init__(self, database: Database):
        self.database = database

    def save(self, station_code: str, readings: list[DailyWeather], attempted_at: str, completed_at: str):
        with self.database.connect() as connection:
            connection.executemany("""
                INSERT INTO weather_readings(station_code, observed_date, precipitation_mm, temperature_max_c, temperature_min_c)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT(station_code, observed_date) DO UPDATE SET
                precipitation_mm=excluded.precipitation_mm, temperature_max_c=excluded.temperature_max_c,
                temperature_min_c=excluded.temperature_min_c
            """, [(station_code, item.observed_date.isoformat(), item.precipitation_mm,
                   item.temperature_max_c, item.temperature_min_c) for item in readings])
            connection.execute("""
                INSERT INTO weather_sync(station_code, last_attempt_at, last_success_at, last_error) VALUES (?, ?, ?, NULL)
                ON CONFLICT(station_code) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,
                last_success_at=excluded.last_success_at, last_error=NULL
            """, (station_code, attempted_at, completed_at))

    def record_error(self, station_code: str, attempted_at: str):
        with self.database.connect() as connection:
            connection.execute("""
                INSERT INTO weather_sync(station_code, last_attempt_at, last_error) VALUES (?, ?, 'source_unavailable')
                ON CONFLICT(station_code) DO UPDATE SET last_attempt_at=excluded.last_attempt_at, last_error=excluded.last_error
            """, (station_code, attempted_at))

    def snapshot(self, station_code: str):
        with self.database.connect() as connection:
            connection.execute("BEGIN")
            state = connection.execute("SELECT * FROM weather_sync WHERE station_code=?", (station_code,)).fetchone()
            rows = connection.execute("""
                SELECT observed_date, precipitation_mm, temperature_max_c, temperature_min_c FROM weather_readings
                WHERE station_code=? ORDER BY observed_date DESC LIMIT 31
            """, (station_code,)).fetchall()
        return dict(state) if state else None, [dict(row) for row in reversed(rows)]
