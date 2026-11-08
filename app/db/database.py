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
        """Inicializa el esquema y migra las columnas de formularios anteriores."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    request_key TEXT UNIQUE,
                    fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    observations TEXT NOT NULL,
                    observed_condition TEXT NOT NULL,
                    situations_json TEXT NOT NULL,
                    other_situation TEXT NOT NULL DEFAULT '',
                    latitude REAL,
                    longitude REAL,
                    accuracy_m REAL,
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
                CREATE TABLE IF NOT EXISTS image_analyses (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    camera_id TEXT NOT NULL,
                    river_id TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'iot' CHECK(source IN ('iot','test')),
                    received_at TEXT NOT NULL,
                    captured_at TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL CHECK(status IN ('queued','processing','analyzed','partial','not_configured','error')),
                    message TEXT NOT NULL DEFAULT '',
                    result_json TEXT,
                    artifacts_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS analyses_camera ON image_analyses(camera_id, sequence DESC);
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL, username_key TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','admin')),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    expires_at INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS sessions_expiry ON auth_sessions(expires_at);
                CREATE TABLE IF NOT EXISTS auth_throttles (
                    bucket TEXT PRIMARY KEY, window_start INTEGER NOT NULL, attempts INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS report_reviews (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id TEXT NOT NULL REFERENCES reports(id), admin_id TEXT NOT NULL REFERENCES users(id),
                    decision TEXT NOT NULL CHECK(decision IN ('pending','validated','discarded')),
                    notes TEXT NOT NULL, created_at TEXT NOT NULL,
                    attention_level TEXT CHECK(attention_level IN ('monitoring','preventive','priority'))
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL,
                    location TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id),
                    active INTEGER NOT NULL DEFAULT 1, closed_at TEXT, closed_by TEXT REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS alert_monitoring_points (
                    camera_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    latitude REAL NOT NULL CHECK(latitude BETWEEN -90 AND 90),
                    longitude REAL NOT NULL CHECK(longitude BETWEEN -180 AND 180),
                    updated_at TEXT NOT NULL, updated_by TEXT NOT NULL REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS public_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    id TEXT PRIMARY KEY, endpoint TEXT NOT NULL UNIQUE, subscription_json TEXT NOT NULL,
                    latitude REAL NOT NULL, longitude REAL NOT NULL, accuracy_m REAL NOT NULL,
                    location_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS push_deliveries (
                    subscription_id TEXT NOT NULL REFERENCES push_subscriptions(id) ON DELETE CASCADE,
                    alert_id TEXT NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
                    attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at INTEGER NOT NULL DEFAULT 0,
                    sent_at INTEGER,
                    PRIMARY KEY(subscription_id, alert_id)
                );
            """)
            connection.execute('BEGIN IMMEDIATE')
            user_columns = {row['name'] for row in connection.execute('PRAGMA table_info(users)')}
            if 'phone' not in user_columns:
                connection.execute('ALTER TABLE users ADD COLUMN phone TEXT')
            discharge_columns = {row['name'] for row in connection.execute('PRAGMA table_info(discharge_readings)')}
            for name in ('yellow_m3s', 'orange_m3s', 'red_m3s'):
                if name not in discharge_columns:
                    connection.execute(f'ALTER TABLE discharge_readings ADD COLUMN {name} REAL')
            alert_columns = {row['name'] for row in connection.execute('PRAGMA table_info(alerts)')}
            for name, definition in {
                'source_type': 'TEXT', 'source_id': 'TEXT', 'latitude': 'REAL',
                'longitude': 'REAL', 'message_key': 'TEXT', 'radius_m': 'INTEGER',
            }.items():
                if name not in alert_columns:
                    connection.execute(f'ALTER TABLE alerts ADD COLUMN {name} {definition}')
            connection.execute('CREATE INDEX IF NOT EXISTS alerts_created ON alerts(created_at DESC, id DESC)')
            columns = {row['name'] for row in connection.execute('PRAGMA table_info(image_analyses)')}
            if 'source' not in columns:
                connection.execute("ALTER TABLE image_analyses ADD COLUMN source TEXT NOT NULL DEFAULT 'iot' CHECK(source IN ('iot','test'))")
            report_columns = {row['name'] for row in connection.execute('PRAGMA table_info(reports)')}
            additions = {
                'client_created_at': 'TEXT',
                'phone': 'TEXT',
                'other_situation': "TEXT NOT NULL DEFAULT ''",
                'review_status': "TEXT NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','validated','discarded'))",
                'reviewed_at': 'TEXT', 'reviewed_by': 'TEXT',
                'review_notes': "TEXT NOT NULL DEFAULT ''", 'review_version': 'INTEGER NOT NULL DEFAULT 0',
                'attention_level': "TEXT CHECK(attention_level IN ('monitoring','preventive','priority'))",
            }
            for name, definition in additions.items():
                if name not in report_columns:
                    connection.execute(f'ALTER TABLE reports ADD COLUMN {name} {definition}')
            connection.execute('CREATE INDEX IF NOT EXISTS reports_review ON reports(review_status, created_at DESC)')
            review_columns = {row['name'] for row in connection.execute('PRAGMA table_info(report_reviews)')}
            if 'attention_level' not in review_columns:
                connection.execute("ALTER TABLE report_reviews ADD COLUMN attention_level TEXT CHECK(attention_level IN ('monitoring','preventive','priority'))")
            for name in ('river_section', 'district', 'reference', 'anonymous',
                         'contact_name', 'contact_phone', 'neighborhood'):
                if name in report_columns:
                    connection.execute(f'ALTER TABLE reports DROP COLUMN {name}')

