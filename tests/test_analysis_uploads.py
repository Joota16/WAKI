"""Subidas manuales: inferencia real sustituida por un doble y datos temporales."""
import io
import sqlite3
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.db.database import Database
from test_analyses import FakeVision, KEY, app_for, photo, upload


def manual(client, *, river='chillon', content=None, key=KEY, filename='foto.jpg'):
    return client.post('/api/analysis-tests', params={'river_id': river},
                       files={'file': (filename, photo() if content is None else content, 'image/jpeg')},
                       headers={'X-IoT-Key': key})


def test_manual_analysis_uses_same_engine_without_changing_camera_or_citizen_reports(tmp_path):
    provider = FakeVision()
    with TestClient(app_for(tmp_path, provider)) as client:
        camera = upload(client, 'red')
        response = manual(client, filename='../../private-file.jpg')
        assert response.status_code == 202, response.text
        pending = response.json()
        assert pending['status'] == 'queued' and pending['source'] == 'test'
        assert pending['frame_id'] is None and pending['camera_id'] is None
        result = client.get('/api/analyses/' + pending['id']).json()
        assert result['status'] == 'analyzed' and result['water_fraction'] == .25
        assert result['source_label'] == 'Prueba manual'
        assert result['result']['input']['source'] == 'test'
        assert result['result']['input']['camera_id'] is None
        assert result['result']['input']['captured_at'] is None
        assert provider.calls[-1][1]['source'] == 'test'
        assert client.get('/api/cameras/chillon-01/latest').json()['latest']['id'] == camera['id']
        assert client.get('/api/cameras/chillon-01/analyses').json()['total'] == 1
        assert client.get('/api/reports').json()['total'] == 0
        assert client.get('/api/analysis-tests?river_id=chillon').json()['items'][0]['id'] == result['id']
        assert client.get('/api/analysis-tests?river_id=rimac').json()['total'] == 0
        html = client.get(result['report_url'] + '/contenido').text
        assert 'Prueba manual' in html and 'No es una captura de la cámara' in html
        assert client.get(result['overlay_url']).status_code == 200
        assert not list((tmp_path / 'photos').iterdir())
        assert not (tmp_path / 'private-file.jpg').exists()


def test_manual_photograph_is_normalized_and_exif_removed(tmp_path):
    buffer = io.BytesIO()
    image = Image.new('RGB', (80, 40), 'green')
    metadata = Image.Exif()
    metadata[274], metadata[315] = 6, 'private author'
    image.save(buffer, 'JPEG', exif=metadata)
    with TestClient(app_for(tmp_path)) as client:
        result = manual(client, content=buffer.getvalue()).json()
        assert result['status'] == 'not_configured'
        assert result['water_fraction'] is None and result['overlay_url'] is None
        assert result['candidate_count'] is None
        with Image.open(io.BytesIO(client.get(result['original_url']).content)) as normalized:
            assert normalized.format == 'JPEG' and normalized.size == (40, 80)
            assert not normalized.getexif()
        assert client.get('/api/cameras/chillon-01/latest').json()['latest'] is None


@pytest.mark.parametrize('key,content,river,status', [
    ('wrong', b'invalid', 'chillon', 401), ('', b'invalid', 'chillon', 401),
    (KEY, b'', 'chillon', 422), (KEY, b'<svg></svg>', 'chillon', 422),
    (KEY, b'not a photo', 'chillon', 422),
    (KEY, None, 'unknown', 422), (KEY, b'x' * (1024 * 1024 + 1), 'chillon', 413),
])
def test_invalid_manual_uploads_do_not_create_jobs(tmp_path, key, content, river, status):
    with TestClient(app_for(tmp_path, FakeVision(), max_upload_mb=1)) as client:
        response = manual(client, key=key, content=content, river=river)
        assert response.status_code == status, response.text
        assert client.get('/api/analysis-tests?river_id=chillon').json()['total'] == 0
        assert not list((tmp_path / 'analyses').iterdir())


def test_manual_model_failure_preserves_photo_and_can_be_retried(tmp_path):
    provider = FakeVision(fail=True)
    with TestClient(app_for(tmp_path, provider)) as client:
        created = manual(client).json()
        result = client.get('/api/analyses/' + created['id']).json()
        assert result['status'] == 'error' and result['result'] is None
        assert client.get(result['original_url']).status_code == 200
        provider.fail = False
        response = client.post('/api/analyses/' + result['id'] + '/retry', headers={'X-IoT-Key': KEY})
        assert response.status_code == 202
        assert client.get('/api/analyses/' + result['id']).json()['status'] == 'analyzed'
        assert provider.calls[-1][1]['source'] == 'test'


def test_manual_retention_and_pagination_are_independent_from_camera(tmp_path):
    with TestClient(app_for(tmp_path, FakeVision(), ai_retention_images=2)) as client:
        camera = upload(client)
        first, second, third = [manual(client).json() for _ in range(3)]
        result = client.get('/api/analysis-tests?river_id=chillon&limit=1').json()
        assert result['total'] == 2 and result['items'][0]['id'] == third['id']
        assert client.get('/api/analysis-tests?river_id=chillon&limit=1&offset=1').json()['items'][0]['id'] == second['id']
        assert client.get('/api/analyses/' + first['id']).status_code == 404
        assert not (tmp_path / 'analyses' / UUID(first['id']).hex).exists()
        assert client.get('/api/analyses/' + camera['id']).status_code == 200
        assert client.get('/api/cameras/chillon-01/latest').json()['latest']['id'] == camera['id']


def test_existing_analysis_schema_is_migrated_without_losing_rows(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    job = uuid4().hex
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE image_analyses (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT NOT NULL UNIQUE, camera_id TEXT NOT NULL, river_id TEXT NOT NULL,
                received_at TEXT NOT NULL, captured_at TEXT, created_at TEXT NOT NULL, completed_at TEXT,
                status TEXT NOT NULL, message TEXT NOT NULL DEFAULT '', result_json TEXT,
                artifacts_json TEXT NOT NULL DEFAULT '{}'
            );
        """)
        connection.execute("""INSERT INTO image_analyses(id, camera_id, river_id, received_at, created_at, status)
            VALUES (?, 'chillon-01', 'chillon', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 'not_configured')""", (job,))
    database = Database(path)
    database.initialize()
    database.initialize()
    with database.connect() as connection:
        row = connection.execute('SELECT * FROM image_analyses').fetchone()
        assert row['id'] == job and row['source'] == 'iot'
        assert connection.execute('SELECT COUNT(*) FROM image_analyses').fetchone()[0] == 1
