import base64
import json
import os
import time
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
import http_ece
from pywebpush import WebPushException
import pytest
import requests

from app.config import Settings
from app.main import create_app
from app.services.notifications import NotificationsService, distance_m
from test_accounts_and_moderation import ADMIN_PASSWORD, csrf, login, register, review
from test_reports import send

HEADERS = {'X-WAKI-Client': 'browser', 'Origin': 'http://testserver'}


def encoded(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def subscription(latitude=-11.913546150295304, longitude=-77.07124450899127):
    key = ec.generate_private_key(ec.SECP256R1())
    return {'token': str(uuid4()), 'subscription': {
        'endpoint': 'https://fcm.googleapis.com/fcm/send/' + uuid4().hex,
        'keys': {'p256dh': encoded(key.public_key().public_bytes(serialization.Encoding.X962,
                                                               serialization.PublicFormat.UncompressedPoint)),
                 'auth': encoded(b'0123456789abcdef')}},
            'latitude': latitude, 'longitude': longitude, 'accuracy_m': 10}, key


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False,
                    admin_username='admin', admin_password=ADMIN_PASSWORD)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as instance:
        yield instance


def alert(client, radius=100):
    login(client)
    result = client.post('/api/alerts', headers=csrf(client), json={
        'kind': 'inundacion', 'source_type': 'camera', 'source_id': 'chillon-01',
        'message_key': 'stay_clear', 'radius_m': radius})
    assert result.status_code == 201, result.text
    return result.json()


def test_publication_gate_covers_all_paths_filters_and_review_transitions(client):
    pending = send(client).json()
    validated = send(client).json()
    login(client)
    validated = review(client, validated, 'validated').json()
    assert client.get('/api/reports?review_status=pending').json()['total'] == 1
    assert client.get(pending['detail_url']).status_code == 200
    assert client.get(pending['photos'][0]['url']).status_code == 200
    guest = TestClient(client.app)
    for signed_in in (False, True):
        if signed_in:
            register(guest, 'nearby-citizen')
        assert guest.get('/api/reports').json()['total'] == 1
        assert guest.get('/api/reports').json()['items'][0]['id'] == validated['id']
        assert pending['id'] not in guest.get('/reportes').text
        for path in [pending['detail_url'], '/api/reports/' + pending['id'], pending['photos'][0]['url']]:
            assert guest.get(path).status_code == 404
        for suffix in ['?review_status=pending', '?review_status=discarded', '?include_discarded=true']:
            assert guest.get('/api/reports' + suffix).status_code == 403
        assert guest.get(validated['detail_url']).status_code == 200
        assert guest.get(validated['photos'][0]['url']).status_code == 200
        assert guest.get('/api/reports/' + validated['id']).json()['review_notes'] is None
    reopened = review(client, validated, 'pending').json()
    assert guest.get(validated['photos'][0]['url']).status_code == 404
    assert guest.get('/api/reports').json()['total'] == 0
    review(client, reopened, 'validated')
    assert guest.get(validated['detail_url']).status_code == 200
    guest.close()


def test_keys_are_private_stable_and_worker_preserves_push_with_offline_form(client, settings):
    config = client.get('/api/notifications/config')
    assert config.status_code == 200 and config.json()['enabled']
    key = config.json()['public_key']
    assert len(base64.urlsafe_b64decode(key + '=')) == 65
    service = NotificationsService(client.app.state.database, settings)
    service.initialize()
    assert service.public_key == key
    if os.name != 'nt':  # Windows usa ACL, no representa estos permisos POSIX en st_mode.
        assert service.private_key.stat().st_mode & 0o777 == 0o600
    assert 'PRIVATE KEY' not in config.text
    worker = client.get('/service-worker.js')
    assert worker.status_code == 200
    assert worker.headers['service-worker-allowed'] == '/'
    assert 'no-cache' in worker.headers['cache-control']
    assert "addEventListener('push'" in worker.text
    assert "addEventListener('fetch'" in worker.text
    assert "addEventListener('sync'" in worker.text
    assert '__WAKI_OFFLINE_VERSION__' not in worker.text


def test_subscription_is_idempotent_owned_by_device_and_can_be_removed(client):
    values, _ = subscription()
    assert client.put('/api/notifications/subscription', headers=HEADERS, json=values).status_code == 200
    assert client.put('/api/notifications/subscription', headers=HEADERS, json=values).status_code == 200
    changed = {**values, 'token': str(uuid4())}
    assert client.put('/api/notifications/subscription', headers=HEADERS, json=changed).status_code == 409
    assert client.put('/api/notifications/subscription', json=values).status_code == 403
    assert client.put('/api/notifications/subscription', headers={**HEADERS, 'Origin': 'https://other.example'}, json=values).status_code == 403
    assert client.request('DELETE', '/api/notifications/subscription', headers=HEADERS,
                          json={'token': changed['token']}).status_code == 204
    with client.app.state.database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM push_subscriptions').fetchone()[0] == 1
    assert client.request('DELETE', '/api/notifications/subscription', headers=HEADERS,
                          json={'token': values['token']}).status_code == 204
    with client.app.state.database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM push_subscriptions').fetchone()[0] == 0


@pytest.mark.parametrize('endpoint', ['http://fcm.googleapis.com/fcm/send/test', 'https://127.0.0.1/private',
    'https://fcm.googleapis.com.evil.example/push', 'https://user:pass@fcm.googleapis.com/push',
    'https://fcm.googleapis.com:444/push', 'https://other.example/push'])
def test_untrusted_push_targets_are_rejected(client, endpoint):
    values, _ = subscription()
    values['subscription']['endpoint'] = endpoint
    assert client.put('/api/notifications/subscription', headers=HEADERS, json=values).status_code == 422


@pytest.mark.parametrize('changes', [{'latitude': 91}, {'longitude': float('inf')}, {'accuracy_m': 1001},
                                    {'accuracy_m': 0}, {'location_at': 9999999999}])
def test_invalid_or_client_dated_locations_are_rejected(client, changes):
    values, _ = subscription()
    # JSON no admite Infinity; enviar el literal como parte del cuerpo comprueba la validación.
    response = client.put('/api/notifications/subscription', headers={**HEADERS, 'Content-Type': 'application/json'},
                          content=json.dumps({**values, **changes}))
    assert response.status_code == 422


def test_only_fresh_nearby_subscribers_receive_and_delivery_survives_restart(client, settings):
    close, _ = subscription()
    far, _ = subscription(latitude=-12.2)
    stale, _ = subscription()
    for values in [close, far, stale]:
        assert client.put('/api/notifications/subscription', headers=HEADERS, json=values).status_code == 200
    service = client.app.state.notifications
    with service.database.connect() as db:
        db.execute('UPDATE push_subscriptions SET location_at=? WHERE id=?',
                   (int(time.time()) - 86401, service.identity(stale['token'])))
    notice = alert(client)
    sent = []
    service.sender = lambda sub, payload: sent.append((sub, payload))
    service.dispatch()
    assert len(sent) == 1 and sent[0][0]['endpoint'] == close['subscription']['endpoint']
    assert sent[0][1]['id'] == notice['id']
    assert sent[0][1]['url'] == '/?aviso=' + notice['id']
    assert '100 m' in sent[0][1]['body']
    restarted = NotificationsService(service.database, settings, sender=service.sender)
    restarted.initialize()
    restarted.dispatch()
    assert len(sent) == 1
    with service.database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM push_subscriptions').fetchone()[0] == 2


def test_delivery_retries_but_not_after_user_moves_or_notice_closes(client):
    values, _ = subscription()
    client.put('/api/notifications/subscription', headers=HEADERS, json=values)
    notice = alert(client)
    service = client.app.state.notifications
    calls = []
    def fail(sub, payload):
        calls.append(payload)
        raise requests.Timeout()
    service.sender = fail
    service.dispatch()
    assert len(calls) == 1
    service.dispatch()
    assert len(calls) == 1
    with service.database.connect() as db:
        db.execute('UPDATE push_deliveries SET next_attempt_at=0')
    moved = {**values, 'latitude': -12.2}
    client.put('/api/notifications/subscription', headers=HEADERS, json=moved)
    service.dispatch()
    assert len(calls) == 1
    client.put('/api/notifications/subscription', headers=HEADERS, json=values)
    service.dispatch()
    assert len(calls) == 2
    assert client.post('/api/alerts/' + notice['id'] + '/close', headers=csrf(client)).status_code == 200
    service.dispatch()
    assert len(calls) == 2


def test_expired_push_endpoint_is_deleted(client):
    values, _ = subscription()
    client.put('/api/notifications/subscription', headers=HEADERS, json=values)
    alert(client)
    response = requests.Response()
    response.status_code = 410
    def expired(sub, payload):
        raise WebPushException('expired', response=response)
    client.app.state.notifications.sender = expired
    client.app.state.notifications.dispatch()
    with client.app.state.database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM push_subscriptions').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM push_deliveries').fetchone()[0] == 0


def test_real_webpush_encryption_and_vapid_without_contacting_external_services(client, monkeypatch):
    values, browser_key = subscription()
    captured = []
    def transport(session, method, url, **kwargs):
        assert kwargs['allow_redirects'] is False
        captured.append(kwargs)
        response = requests.Response()
        response.status_code = 201
        return response
    monkeypatch.setattr(requests.Session, 'request', transport)
    client.app.state.notifications.send(values['subscription'], {'title': 'Aviso de prueba'})
    assert len(captured) == 1
    headers = {key.lower(): value for key, value in captured[0]['headers'].items()}
    assert headers['authorization'].startswith('vapid ')
    assert headers['ttl'] == '60' or headers['ttl'] == 60
    plain = http_ece.decrypt(captured[0]['data'], private_key=browser_key,
                             auth_secret=b'0123456789abcdef', version='aes128gcm')
    assert json.loads(plain) == {'title': 'Aviso de prueba'}


def test_disabled_push_and_configured_capture_frequency(settings):
    settings = settings.model_copy(update={'push_enabled': False, 'camera_capture_seconds': 90})
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/notifications/config').json()['enabled'] is False
        values, _ = subscription()
        assert client.put('/api/notifications/subscription', headers=HEADERS, json=values).status_code == 503
        latest = client.get('/api/cameras/chillon-01/latest').json()
        assert latest['capture_interval_seconds'] == 90
        assert latest['poll_seconds'] == 5
        assert 'capturar cada 90 segundos' in client.get('/').text
        assert not (settings.data_dir / '.webpush-private.pem').exists()


def test_geographic_distance_respects_zone_boundary_and_dateline():
    assert distance_m(0, 0, 0, 0) == 0
    assert distance_m(0, 0, 0, 0.00089) < 100
    assert distance_m(0, 0, 0, 0.00091) > 100
    assert distance_m(0, 179.9999, 0, -179.9999) < 30
