from datetime import datetime
import io
import json
from uuid import uuid4
from typing import get_args

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.config import Settings
from app.main import create_app
from app.schemas.reports import Situation
from app.schemas.reports import ReportReview
from app.schemas.auth import Credentials


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(_env_file=None, senamhi_enabled=False, data_dir=tmp_path))) as instance:
        yield instance


def image_bytes(color="blue", exif=False):
    output = io.BytesIO()
    image = Image.new("RGB", (80, 40), color)
    metadata = Image.Exif()
    if exif:
        metadata[274] = 6
        metadata[315] = "Dato privado de prueba"
    image.save(output, "JPEG", exif=metadata)
    return output.getvalue()


def payload(**changes):
    return {"observations": "Observación de prueba", "observed_condition": "normal",
            "latitude": -11.8924, "longitude": -77.0682,
            "accuracy_m": 15, **changes}


def send(client, values=None, photos=None, headers=None):
    return client.post("/api/reports", data={"metadata": json.dumps(values if values is not None else payload())},
                       files=photos or [("files", ("foto.jpg", image_bytes(), "image/jpeg"))], headers=headers or {})


def publish_report(client, report):
    """Prepara datos ya revisados para pruebas de consulta pública."""
    auth = client.app.state.auth
    actor = auth.repository.by_username('test-reviewer')
    if actor is None:
        user = auth._create_user(Credentials(username='test-reviewer', password='only-a-test-reviewer-password'), 'admin')
        actor = {'id': str(user.id)}
    return client.app.state.reports.review(report['id'], ReportReview(
        decision='validated', expected_version=report.get('review_version', 0),
        attention_level='monitoring', notes='Verificado para esta prueba'), actor['id']).model_dump(mode='json')


def test_save_retrieve_photos_and_privacy(client):
    response = send(client, payload(),
                    [("files", ("../../original.jpg", image_bytes(exif=True), "text/plain")),
                     ("files", ("segunda.jpg", image_bytes("green"), "image/jpeg"))])
    assert response.status_code == 201, response.text
    report = response.json()
    assert datetime.fromisoformat(report["created_at"]).utcoffset().total_seconds() == 0
    assert report["analysis_status"] == "not_configured"
    assert len(report["photos"]) == 2
    assert all(key not in report for key in ("river_section", "district", "reference", "anonymous",
                                           "contact_name", "contact_phone", "neighborhood"))
    assert client.get(f"/api/reports/{report['id']}").status_code == 404
    assert client.get(report['photos'][0]['url']).status_code == 404
    publish_report(client, report)
    report = client.get(f"/api/reports/{report['id']}").json()
    assert client.get(f"/api/reports/{report['id']}").json() == report
    assert client.get("/api/reports").json()["total"] == 1
    photo = client.get(report["photos"][0]["url"])
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(photo.content)) as normalized:
        assert normalized.size == (40, 80), "Se debe respetar la orientación EXIF."
        assert not normalized.getexif(), "No deben publicarse metadatos EXIF."
    detail = client.get(report["detail_url"])
    assert detail.status_code == 200
    assert "Observación de prueba" in detail.text
    assert not (client.app.state.settings.data_dir / "original.jpg").exists()


def test_minimal_report_without_coordinates_or_removed_blocks(client):
    response = send(client, {"observed_condition": "normal"})
    assert response.status_code == 201
    report = response.json()
    assert report["latitude"] is None and report["longitude"] is None
    assert report["observations"] == ""
    row = client.app.state.reports.repository.get(report["id"], include_discarded=True)
    assert all(key not in row for key in ("river_section", "district", "reference", "anonymous",
                                        "contact_name", "contact_phone", "neighborhood"))
    publish_report(client, report)
    assert "Sin coordenadas." in client.get(report["detail_url"]).text


def test_other_situation_persists_with_all_options_and_escaped_detail(tmp_path):
    settings = Settings(_env_file=None, senamhi_enabled=False, data_dir=tmp_path)
    description = "Puente con grietas.\n<script>alert('otros')</script>"
    values = payload(situations=list(get_args(Situation)), other_situation=f"  {description}  ")
    headers = {"Idempotency-Key": str(uuid4())}
    with TestClient(create_app(settings)) as client:
        response = send(client, values, headers=headers)
        assert response.status_code == 201, response.text
        report = response.json()
        assert report['other_situation'] == description
        assert len(report['situations']) == 7
        assert report['observations'] == values['observations']
        assert send(client, values, headers=headers).json()['id'] == report['id']
        assert send(client, {**values, 'other_situation': 'Otro detalle'}, headers=headers).status_code == 409
        publish_report(client, report)

    with TestClient(create_app(settings)) as client:
        saved = client.get('/api/reports/' + report['id']).json()
        assert saved['other_situation'] == description
        assert client.get('/api/reports').json()['items'][0]['other_situation'] == description
        detail = client.get(saved['detail_url']).text
        assert 'Otros: Puente con grietas.' in detail
        assert '&lt;script&gt;' in detail
        assert "<script>alert('otros')</script>" not in detail
        assert client.get(saved['photos'][0]['url']).status_code == 200


@pytest.mark.parametrize('situations,description', [
    (['Otros'], ''), (['Otros'], '   '), (['Otros'], 'x' * 501),
    ([], 'Texto sin seleccionar Otros'),
])
def test_other_situation_requires_selection_and_description(client, situations, description):
    response = send(client, payload(situations=situations, other_situation=description))
    assert response.status_code == 422
    assert client.get('/api/reports').json()['total'] == 0
    assert not list(client.app.state.reports.images.directory.iterdir())


def test_other_situation_accepts_maximum_length(client):
    response = send(client, payload(situations=['Otros'], other_situation='x' * 500))
    assert response.status_code == 201
    assert response.json()['other_situation'] == 'x' * 500


@pytest.mark.parametrize("field,value", [
    ("river_section", "Río Chillón"), ("district", "Comas"), ("reference", "Puente de prueba"),
    ("anonymous", True), ("contact_name", "Nombre de prueba"), ("contact_phone", "999111222"),
    ("neighborhood", "Barrio de prueba"),
])
def test_removed_fields_are_rejected_and_not_saved(client, field, value):
    response = send(client, payload(**{field: value}))
    assert response.status_code == 422
    assert client.get("/api/reports").json()["total"] == 0
    assert not list(client.app.state.reports.images.directory.iterdir())


@pytest.mark.parametrize("changes", [
    {"latitude": 91}, {"longitude": -181}, {"latitude": None}, {"longitude": float("inf")},
    {"observations": "x" * 2001},
    {"observed_condition": "inventado"}, {"situations": ["inventado"]},
])
def test_invalid_metadata_has_no_side_effects(client, changes):
    response = send(client, payload(**changes))
    assert response.status_code == 422
    assert client.get("/api/reports").json()["total"] == 0
    assert not list(client.app.state.reports.images.directory.iterdir())


@pytest.mark.parametrize("content,mime", [(b"", "image/jpeg"), (b"<svg></svg>", "image/png"), (b"not an image", "image/jpeg")])
def test_real_file_content_is_validated(client, content, mime):
    response = send(client, photos=[("files", ("fake.jpg", content, mime))])
    assert response.status_code == 422
    assert client.get("/api/reports").json()["total"] == 0


def test_invalid_second_photo_cleans_first(client):
    response = send(client, photos=[("files", ("good.jpg", image_bytes(), "image/jpeg")),
                                   ("files", ("bad.jpg", b"broken", "image/jpeg"))])
    assert response.status_code == 422
    assert not list(client.app.state.reports.images.directory.iterdir())


def test_database_failure_cleans_files(client, monkeypatch):
    def fail(*args):
        raise RuntimeError("Simulated storage failure")
    monkeypatch.setattr(client.app.state.reports.repository, "create", fail)
    with pytest.raises(RuntimeError, match="Simulated storage failure"):
        send(client)
    assert not list(client.app.state.reports.images.directory.iterdir())


def test_limits_on_count_bytes_and_pixels(tmp_path):
    settings = Settings(_env_file=None, senamhi_enabled=False, data_dir=tmp_path, max_photos=1, max_upload_mb=1, max_image_pixels=100)
    with TestClient(create_app(settings)) as client:
        photo = ("files", ("small.jpg", image_bytes(), "image/jpeg"))
        assert send(client, photos=[photo, photo]).status_code == 422
        assert send(client, photos=[("files", ("large.jpg", b"x" * (1024 * 1024 + 1), "image/jpeg"))]).status_code == 413
        assert send(client).status_code == 413  # 80 x 40 excede los 100 píxeles configurados.
        assert client.post("/api/reports", content=b"x", headers={"Content-Length": str(3 * 1024 * 1024)}).status_code == 413


def test_missing_file_and_malformed_metadata(client):
    assert client.post("/api/reports", data={"metadata": json.dumps(payload())}).status_code == 422
    assert client.post("/api/reports", data={"metadata": "{"},
                       files=[("files", ("photo.jpg", image_bytes(), "image/jpeg"))]).status_code == 422


def test_request_limit_without_content_length(tmp_path):
    with TestClient(create_app(Settings(_env_file=None, senamhi_enabled=False, data_dir=tmp_path, max_photos=1, max_upload_mb=1))) as client:
        def chunks():
            yield b'--boundary\r\nContent-Disposition: form-data; name="files"; filename="large.jpg"\r\n\r\n'
            yield b'x' * (3 * 1024 * 1024)
        response = client.post('/api/reports', content=chunks(),
                               headers={'Content-Type': 'multipart/form-data; boundary=boundary'})
        assert response.status_code == 413
        assert client.get('/api/reports').json()['total'] == 0


def test_idempotent_retries_and_conflict(client):
    headers = {"Idempotency-Key": str(uuid4())}
    first = send(client, headers=headers)
    second = send(client, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert client.get("/api/reports").json()["total"] == 0
    with client.app.state.database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM reports').fetchone()[0] == 1
    assert len(list(client.app.state.reports.images.directory.iterdir())) == 1
    assert send(client, payload(observations="Otro contenido"), headers=headers).status_code == 409


def test_persistence_and_public_html_escaping(tmp_path):
    settings = Settings(_env_file=None, senamhi_enabled=False, data_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        report = send(client, payload(observations="<script>alert('x')</script>")).json()
        publish_report(client, report)
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/reports/{report['id']}").status_code == 200
        assert client.get(report["photos"][0]["url"]).status_code == 200
        assert "&lt;script&gt;" in client.get(report["detail_url"]).text
        assert client.get("/api/reports?limit=1&offset=1").json()["items"] == []
        assert client.get("/api/reports?limit=0").status_code == 422
        assert client.get(f"/api/reports/{uuid4()}").status_code == 404
        assert client.get(f"/api/reports/{uuid4()}/photos/{report['photos'][0]['id']}").status_code == 404


def test_real_html_listing_contains_saved_photos_and_escaped_observations(client):
    first = send(client, payload(observations="Primera observación real")).json()
    second = send(client, payload(observations="<script>alert('listado')</script>")).json()
    publish_report(client, first)
    publish_report(client, second)
    response = client.get('/reportes')
    assert response.status_code == 200
    assert '2 reportes registrados' in response.text
    assert response.text.index(second['detail_url']) < response.text.index(first['detail_url'])
    assert first['photos'][0]['url'] in response.text
    assert 'Primera observación real' in response.text
    assert '&lt;script&gt;' in response.text
    assert "<script>alert('listado')</script>" not in response.text
    assert 'Validado por la administración' in response.text
    detail = client.get(first['detail_url'])
    assert 'Todos los reportes' in detail.text
    assert 'href="/reportes"' in client.get('/').text


def test_html_listing_pagination(client):
    identifiers = [publish_report(client, send(client, payload(observations=f'Observación {index}')).json())['id'] for index in range(13)]
    first_page = client.get('/reportes')
    assert '13 reportes registrados' in first_page.text
    assert 'Mostrando 1–12 de 13' in first_page.text
    assert identifiers[-1] in first_page.text and identifiers[0] not in first_page.text
    assert 'rel="next"' in first_page.text
    second_page = client.get('/reportes?page=2')
    assert 'Mostrando 13–13 de 13' in second_page.text
    assert identifiers[0] in second_page.text and identifiers[-1] not in second_page.text
    assert 'rel="prev"' in second_page.text
    assert 'rel="next"' not in second_page.text
    overflow = client.get('/reportes?page=100')
    assert overflow.history[0].status_code == 303
    assert str(overflow.url).endswith('/reportes?page=2')
    assert client.get('/reportes?page=0').status_code == 422


def test_html_listing_database_error(client, monkeypatch):
    import sqlite3

    def fail(*args):
        raise sqlite3.OperationalError('Detalle interno que no debe publicarse')
    monkeypatch.setattr(client.app.state.reports, 'list', fail)
    response = client.get('/reportes')
    assert response.status_code == 503
    assert 'No se pudieron consultar los reportes' in response.text
    assert 'Volver a intentar' in response.text
    assert 'Detalle interno' not in response.text


@pytest.mark.parametrize('accuracy,warning', [(15, False), (18726, True)])
def test_report_location_accuracy_is_not_presented_as_exact_gps(client, accuracy, warning):
    report = send(client, payload(accuracy_m=accuracy)).json()
    publish_report(client, report)
    detail = client.get(report['detail_url'])
    assert 'Radio de precisión indicado por el navegador' in detail.text
    assert 'Precisión GPS' not in detail.text
    assert ('Ubicación aproximada de baja precisión' in detail.text) == warning
    if warning:
        assert '18.7 km' in detail.text
    persisted = client.get(f"/api/reports/{report['id']}").json()
    assert persisted['accuracy_m'] == accuracy
    assert persisted['latitude'] == report['latitude']
    assert persisted['longitude'] == report['longitude']
