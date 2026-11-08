from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from test_reports import payload, send, publish_report


def test_device_date_persists_separately_and_retries_are_idempotent(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False)
    values = payload(client_created_at='2026-01-02T08:30:00-05:00')
    key = {'Idempotency-Key': str(uuid4())}
    with TestClient(create_app(settings)) as client:
        report = send(client, values, headers=key).json()
        assert datetime.fromisoformat(report['client_created_at']) == datetime(2026, 1, 2, 13, 30, tzinfo=timezone.utc)
        assert report['created_at'] != report['client_created_at']
        assert send(client, values, headers=key).json()['id'] == report['id']
        assert send(client, {**values, 'client_created_at': '2026-01-03T13:30:00Z'}, headers=key).status_code == 409
        publish_report(client, report)
    with TestClient(create_app(settings)) as client:
        saved = client.get('/api/reports/' + report['id']).json()
        assert saved['client_created_at'] == report['client_created_at']
        html = client.get(report['detail_url']).text
        assert '02/01/2026 08:30' in html
        assert 'fecha indicada por el dispositivo' in html


@pytest.mark.parametrize('date', ['sin fecha', '2026-01-02T08:30:00'])
def test_device_date_requires_timezone(tmp_path, date):
    with TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False))) as client:
        assert send(client, payload(client_created_at=date)).status_code == 422


def test_old_database_adds_nullable_device_date_and_preserves_retry(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False)
    key = {'Idempotency-Key': str(uuid4())}
    with TestClient(create_app(settings)) as client:
        report = send(client, headers=key).json()
        assert report['client_created_at'] is None
        with client.app.state.database.connect() as db:
            db.execute('ALTER TABLE reports DROP COLUMN client_created_at')
    with TestClient(create_app(settings)) as client:
        retry = send(client, headers=key)
        assert retry.status_code == 201
        assert retry.json()['id'] == report['id']
        assert retry.json()['client_created_at'] is None


def test_offline_resources_are_public_local_and_complete(tmp_path):
    with TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False,
                                       report_upload_timeout_seconds=180))) as client:
        assets = client.get('/pwa-assets.json').json()['assets']
        assert assets
        assert all(url.startswith('/static/') for url in assets)
        assert '/static/fonts/material-symbols-outlined.woff2' in assets
        for url in assets:
            assert client.get(url).status_code == 200, url
        form = client.get('/reportar').text
        assert 'data-upload-timeout-seconds="180"' in form
        assert 'cdn.tailwindcss.com' not in form
        assert 'fonts.googleapis.com' not in form
        assert 'reportOutboxList' in form
        worker = client.get('/service-worker.js').text
        assert '__WAKI_OFFLINE_VERSION__' not in worker
