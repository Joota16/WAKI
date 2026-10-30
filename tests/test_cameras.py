from datetime import datetime, timedelta, timezone
import io
import json
import sqlite3
from uuid import uuid4
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from app.config import Settings
from app.main import create_app

KEY = 'test-camera-key-never-used-by-a-real-device'


def photograph(color='blue', exif=False):
    output = io.BytesIO()
    image = Image.new('RGB', (80, 40), color)
    metadata = Image.Exif()
    if exif:
        metadata[274], metadata[315] = 6, 'Private camera metadata'
    image.save(output, 'JPEG', exif=metadata)
    return output.getvalue()


def upload(client, camera='chillon-01', content=None, **headers):
    return client.post('/api/iot/upload', params={'camera_id': camera},
                       content=photograph() if content is None else content,
                       headers={'Content-Type': 'image/jpeg', 'X-IoT-Key': KEY, **headers})


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False, iot_key=KEY)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as instance:
        yield instance


def test_empty_camera_has_no_fabricated_image_or_date(client):
    response = client.get('/api/cameras/chillon-01/latest')
    data = response.json()
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert data['latest'] is None and data['camera']['river_id'] == 'chillon'
    assert data['poll_seconds'] == 5
    assert datetime.fromisoformat(data['server_time']).utcoffset().total_seconds() == 0
    html = client.get('/').text
    assert 'Esperando la primera captura del ESP32' in html
    assert 'FPS: 30' not in html and '(En vivo)' not in html
    assert 'cam-water-path' not in html and KEY not in html


def test_authenticated_image_is_normalized_and_immediately_available(client):
    before = datetime.now(timezone.utc)
    response = upload(client, content=photograph(exif=True))
    assert response.status_code == 201, response.text
    frame = response.json()
    assert frame['captured_at'] is None
    assert datetime.fromisoformat(frame['received_at']) >= before
    assert frame['width'] == 40 and frame['height'] == 80
    assert 'filename' not in frame and KEY not in response.text
    latest = client.get('/api/cameras/chillon-01/latest').json()
    assert latest['latest'] == frame
    assert client.get('/api/cameras/rimac-01/latest').json()['latest'] is None
    image_response = client.get(frame['image_url'])
    assert image_response.headers['content-type'] == 'image/jpeg'
    assert image_response.headers['x-content-type-options'] == 'nosniff'
    with Image.open(io.BytesIO(image_response.content)) as normalized:
        assert not normalized.getexif() and normalized.format == 'JPEG'
    assert client.get('/api/reports').json()['total'] == 0


def test_missing_wrong_and_unconfigured_key_do_not_save_images(client, tmp_path):
    for key in ['', 'wrong-key']:
        assert upload(client, **{'X-IoT-Key': key}).status_code == 401
    assert client.get('/api/cameras/chillon-01/latest').json()['latest'] is None
    assert not list(client.app.state.cameras.images.directory.iterdir())
    no_key = Settings(_env_file=None, data_dir=tmp_path / 'disabled', senamhi_enabled=False, iot_key='')
    with TestClient(create_app(no_key)) as disabled:
        assert upload(disabled).status_code == 503


@pytest.mark.parametrize('content,headers,status', [
    (b'', {}, 422), (b'not a JPEG', {}, 422),
    (b'{"image":"base64"}', {'Content-Type': 'application/json'}, 415),
    (b'fake multipart', {'Content-Type': 'multipart/form-data; boundary=abc'}, 415),
    (b'fake', {'X-Captured-At': '2026-01-01T10:00:00'}, 422),
    (b'fake', {'X-Captured-At': 'invalid'}, 422),
])
def test_invalid_files_and_dates_do_not_create_frames(client, content, headers, status):
    assert upload(client, content=content, **headers).status_code == status
    assert client.get('/api/cameras/chillon-01/latest').json()['latest'] is None
    assert not list(client.app.state.cameras.images.directory.iterdir())


def test_capture_clock_is_optional_utc_and_cannot_be_in_the_future(client):
    captured = datetime.now(timezone.utc) - timedelta(hours=1)
    first = upload(client, **{'X-Captured-At': captured.isoformat()}).json()
    assert datetime.fromisoformat(first['captured_at']) == captured
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert upload(client, **{'X-Captured-At': future.isoformat()}).status_code == 422
    second = upload(client, **{'X-Captured-At': (captured - timedelta(hours=1)).isoformat()}).json()
    assert client.get('/api/cameras/chillon-01/latest').json()['latest']['id'] == second['id']
    assert first['image_url'] != second['image_url']


def test_camera_identity_and_image_paths_are_isolated(client):
    assert upload(client, camera='unknown').status_code == 404
    assert upload(client, camera='../../photos').status_code == 422
    frame = upload(client).json()
    assert client.get(frame['image_url'].replace('chillon-01', 'rimac-01')).status_code == 404
    assert client.get(f'/api/cameras/chillon-01/frames/{uuid4()}/image').status_code == 404
    assert client.get('/api/cameras/unknown/latest').status_code == 404


def test_raw_upload_size_and_real_pixel_limits(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False, iot_key=KEY,
                        max_upload_mb=1, max_image_pixels=100)
    with TestClient(create_app(settings)) as client:
        assert upload(client, content=b'x' * (1024 * 1024 + 1)).status_code == 413
        assert upload(client).status_code == 413
        def chunks():
            for _ in range(3): yield b'x' * (512 * 1024)
        response = client.post('/api/iot/upload?camera_id=chillon-01', content=chunks(),
                               headers={'X-IoT-Key': KEY, 'Content-Type': 'image/jpeg'})
        assert response.status_code == 413
        assert not list(client.app.state.cameras.images.directory.iterdir())


def test_database_failure_removes_new_file_and_keeps_previous_image(client, monkeypatch):
    frame = upload(client).json()
    def fail(*args): raise sqlite3.OperationalError('simulated database failure')
    monkeypatch.setattr(client.app.state.cameras.repository, 'add', fail)
    with pytest.raises(sqlite3.OperationalError): upload(client, content=photograph('red'))
    assert client.get('/api/cameras/chillon-01/latest').json()['latest'] == frame
    assert len(list(client.app.state.cameras.images.directory.iterdir())) == 1


def test_retention_and_restart_preserve_other_cameras_and_citizen_reports(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False, iot_key=KEY, iot_retention_images=2)
    with TestClient(create_app(settings)) as client:
        report = client.post('/api/reports', data={'metadata': json.dumps({
            'observed_condition': 'normal',
        })}, files=[('files', ('citizen.jpg', photograph(), 'image/jpeg'))]).json()
        first = upload(client).json()
        rimac = upload(client, camera='rimac-01').json()
        upload(client, content=photograph('red'))
        last = upload(client, content=photograph('green')).json()
        assert client.get(first['image_url']).status_code == 404
        assert client.get(rimac['image_url']).status_code == 200
        assert len(list(client.app.state.cameras.images.directory.glob('*.jpg'))) == 3
        orphan = client.app.state.cameras.images.directory / 'uncommitted.jpg'
        orphan.write_bytes(b'interrupted upload')
    with TestClient(create_app(settings)) as client:
        assert not orphan.exists()
        assert client.get('/api/cameras/chillon-01/latest').json()['latest'] == last
        assert client.get(last['image_url']).status_code == 200
        assert client.get(report['photos'][0]['url']).status_code == 200
        assert client.get('/api/reports').json()['total'] == 1
