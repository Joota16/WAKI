import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        """Crea el esquema de reportes sin eliminar datos existentes."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    request_key TEXT UNIQUE,
                    fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    river_section TEXT NOT NULL,
                    district TEXT NOT NULL,
                    reference TEXT NOT NULL,
                    observations TEXT NOT NULL,
                    observed_condition TEXT NOT NULL,
                    situations_json TEXT NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    accuracy_m REAL,
                    anonymous INTEGER NOT NULL,
                    contact_name TEXT NOT NULL,
                    contact_phone TEXT NOT NULL,
                    neighborhood TEXT NOT NULL,
                    CHECK ((latitude IS NULL AND longitude IS NULL) OR
                        (latitude IS NOT NULL AND longitude IS NOT NULL AND
                         latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180))
                );
                CREATE INDEX IF NOT EXISTS reports_created ON reports(created_at DESC, id DESC);
                CREATE TABLE IF NOT EXISTS report_photos (
                    id TEXT PRIMARY KEY,
                    report_id TEXT NOT NULL REFERENCES reports(id),
                    filename TEXT NOT NULL UNIQUE,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    size_bytes INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS photos_report ON report_photos(report_id);
                CREATE TABLE IF NOT EXISTS hydrology_readings (
                    station_code TEXT NOT NULL,
                    observed_date TEXT NOT NULL,
                    level_m REAL,
                    PRIMARY KEY(station_code, observed_date)
                );
                CREATE TABLE IF NOT EXISTS hydrology_sync (
                    station_code TEXT PRIMARY KEY,
                    last_attempt_at TEXT NOT NULL,
                    last_success_at TEXT,
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS discharge_readings (
                    station_code TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    discharge_m3s REAL,
                    PRIMARY KEY(station_code, observed_at)
                );
                CREATE TABLE IF NOT EXISTS discharge_sync (
                    station_code TEXT PRIMARY KEY,
                    source_url TEXT,
                    last_attempt_at TEXT NOT NULL,
                    last_success_at TEXT,
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS weather_readings (
                    station_code TEXT NOT NULL,
                    observed_date TEXT NOT NULL,
                    precipitation_mm REAL,
                    temperature_max_c REAL,
                    temperature_min_c REAL,
                    PRIMARY KEY(station_code, observed_date)
                );
                CREATE TABLE IF NOT EXISTS weather_sync (
                    station_code TEXT PRIMARY KEY,
                    last_attempt_at TEXT NOT NULL,
                    last_success_at TEXT,
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS camera_frames (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    camera_id TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    captured_at TEXT,
                    filename TEXT NOT NULL UNIQUE,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    size_bytes INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS camera_latest ON camera_frames(camera_id, sequence DESC);
            """)

