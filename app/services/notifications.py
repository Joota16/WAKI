import asyncio
import base64
import hashlib
import json
import logging
import os
import sqlite3
import time
from math import asin, cos, radians, sin, sqrt

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import webpush, WebPushException
import requests

from app.config import Settings
from app.db.database import Database
from app.schemas.notifications import NearbySubscription

logger = logging.getLogger(__name__)


def distance_m(lat1, lon1, lat2, lon2):
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6_371_000 * 2 * asin(sqrt(min(1, a)))


class NoRedirectSession(requests.Session):
    def request(self, *args, **kwargs):
        kwargs['allow_redirects'] = False
        return super().request(*args, **kwargs)


class NotificationsService:
    def __init__(self, database: Database, settings: Settings, sender=None):
        self.database, self.settings = database, settings
        self.sender = sender or self.send
        self.private_key = settings.data_dir / '.webpush-private.pem'
        self.public_key = None

    def initialize(self):
        if not self.settings.push_enabled:
            return
        if not self.private_key.exists():
            key = ec.generate_private_key(ec.SECP256R1())
            content = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption())
            try:
                fd = os.open(self.private_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, 'wb') as out:
                    out.write(content)
        key = serialization.load_pem_private_key(self.private_key.read_bytes(), password=None)
        raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.public_key = base64.urlsafe_b64encode(raw).decode().rstrip('=')

    @staticmethod
    def identity(token):
        return hashlib.sha256(str(token).encode()).hexdigest()

    def subscribe(self, values: NearbySubscription):
        now = int(time.time())
        identity = self.identity(values.token)
        with self.database.connect() as db:
            db.execute('DELETE FROM push_subscriptions WHERE location_at<?',
                       (now - self.settings.push_location_max_age_seconds,))
            try:
                db.execute('''INSERT INTO push_subscriptions
                    (id,endpoint,subscription_json,latitude,longitude,accuracy_m,location_at) VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET endpoint=excluded.endpoint, subscription_json=excluded.subscription_json,
                    latitude=excluded.latitude, longitude=excluded.longitude, accuracy_m=excluded.accuracy_m,
                    location_at=excluded.location_at''',
                           (identity, values.subscription.endpoint, values.subscription.model_dump_json(),
                            values.latitude, values.longitude, values.accuracy_m, now))
            except sqlite3.IntegrityError as exc:
                raise ValueError('Este navegador ya tiene otra configuración de avisos. Desactívala antes de cambiarla.') from exc
        return now

    def unsubscribe(self, token):
        with self.database.connect() as db:
            db.execute('DELETE FROM push_subscriptions WHERE id=?', (self.identity(token),))

    def send(self, subscription, payload):
        with NoRedirectSession() as session:
            return webpush(subscription_info=subscription, data=json.dumps(payload, ensure_ascii=False),
                           vapid_private_key=str(self.private_key), vapid_claims={'sub': self.settings.push_subject},
                           ttl=60, timeout=8, headers={'Urgency': 'high'}, requests_session=session)

    def dispatch(self):
        """Cola persistente: solo zonas activas y ubicaciones compartidas vigentes."""
        now = int(time.time())
        cutoff = now - self.settings.push_location_max_age_seconds
        with self.database.connect() as db:
            db.execute('DELETE FROM push_subscriptions WHERE location_at<?', (cutoff,))
            db.execute('DELETE FROM push_deliveries WHERE alert_id IN (SELECT id FROM alerts WHERE active=0)')
            subscribers = db.execute('SELECT * FROM push_subscriptions').fetchall()
            alerts = db.execute('SELECT * FROM alerts WHERE active=1 AND radius_m IS NOT NULL AND latitude IS NOT NULL').fetchall()
            for sub in subscribers:
                for alert in alerts:
                    if distance_m(sub['latitude'], sub['longitude'], alert['latitude'], alert['longitude']) <= alert['radius_m']:
                        db.execute('INSERT OR IGNORE INTO push_deliveries(subscription_id,alert_id) VALUES (?,?)',
                                   (sub['id'], alert['id']))
            pending = db.execute('''SELECT d.*, s.subscription_json, s.latitude AS user_latitude,
                s.longitude AS user_longitude, a.title, a.location, a.message, a.latitude, a.longitude, a.radius_m
                FROM push_deliveries d JOIN push_subscriptions s ON s.id=d.subscription_id
                JOIN alerts a ON a.id=d.alert_id WHERE d.sent_at IS NULL AND d.attempts<5 AND d.next_attempt_at<=?
                AND a.active=1 AND s.location_at>=? LIMIT 25''', (now, cutoff)).fetchall()
        for row in pending:
            if distance_m(row['user_latitude'], row['user_longitude'], row['latitude'], row['longitude']) > row['radius_m']:
                continue
            with self.database.connect() as db:
                claimed = db.execute('''UPDATE push_deliveries SET attempts=attempts+1,next_attempt_at=?
                    WHERE subscription_id=? AND alert_id=? AND sent_at IS NULL AND next_attempt_at<=?''',
                                     (now + 60, row['subscription_id'], row['alert_id'], now)).rowcount
            if not claimed:
                continue
            payload = {'id': row['alert_id'], 'title': row['title'],
                       'body': f"{row['location']} · Zona de peligro: {row['radius_m']} m. {row['message'][:500]}",
                       'url': f"/?aviso={row['alert_id']}"}
            try:
                self.sender(json.loads(row['subscription_json']), payload)
            except WebPushException as exc:
                if exc.response is not None and exc.response.status_code in (404, 410):
                    with self.database.connect() as db:
                        db.execute('DELETE FROM push_subscriptions WHERE id=?', (row['subscription_id'],))
                # No registrar endpoints, claves ni ubicaciones.
                logger.warning('No se pudo entregar una notificación; se reintentará si sigue vigente.')
            except Exception:
                logger.warning('Servicio de notificaciones temporalmente no disponible.')
            else:
                with self.database.connect() as db:
                    db.execute('UPDATE push_deliveries SET sent_at=? WHERE subscription_id=? AND alert_id=?',
                               (now, row['subscription_id'], row['alert_id']))

    async def run(self):
        if not self.settings.push_enabled:
            return
        while True:
            await asyncio.sleep(5)
            try:
                await asyncio.to_thread(self.dispatch)
            except Exception:
                logger.exception('No se pudo procesar la cola de notificaciones.')
