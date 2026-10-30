"""Flujo IoT -> IA -> informe usando almacenamiento temporal y dobles de inferencia."""
import io
import json
from pathlib import Path
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
import pytest

from app.config import Settings
from app.main import create_app
from app.repositories.analyses import AnalysesRepository
from app.services.processing import ProcessingService
from app.vision.providers.waki import WakiProvider

KEY = 'test-key-for-analysis-only'


def photo(color='blue'):
    stream = io.BytesIO()
    Image.new('RGB', (120, 80), color).save(stream, 'JPEG')
    return stream.getvalue()


class FakeVision:
    """Nunca se instala como proveedor de producción ni usa predicciones de replay."""
    def __init__(self, fail=False, water=True, objects=True, empty=False):
        self.fail, self.water, self.objects, self.empty = fail, water, objects, empty
        self.calls = []

    def configuration_issue(self, river_id):
        return None

    def analyze(self, image, context, output):
        self.calls.append((Path(image).read_bytes(), context))
        if self.fail:
            raise RuntimeError('Private internal error and server paths')
        rgb = Image.open(image).convert('RGB')
        marked = rgb.copy()
        ImageDraw.Draw(marked).rectangle([10, 10, 80, 60], outline='yellow', width=3)
        marked.save(output / 'analisis_combinado.jpg')
        candidate = {'candidate_id': 'OBJ-001', 'review_region_id': 'ZONA-001', 'label_es': 'Botella de plástico',
                     'source_models': ['grounding_dino'], 'bbox_xyxy': [10, 10, 80, 60]}
        result = {
            'schema_version': '4.1', 'analysis_mode': 'live_models', 'input': context,
            'modules': {
                'water_segmentation': {'status': 'predicted_empty_needs_review' if self.empty else 'predicted_nonempty',
                                       'fraction_of_image_predicted_as_water': 0.0 if self.empty else .25}
                                      if self.water else {'status': 'error'},
                'object_candidates': {'model_status': {'grounding_dino': {'status': 'processed' if self.objects else 'disabled'}},
                                      'candidates': ([] if self.empty or not self.objects else [candidate])},
            },
            'summary': {'observations': ['Resultado de prueba'], 'risk_level': None, 'inspection_priority': None},
        }
        return result, {'combined_overlay': 'analisis_combinado.jpg'}


def app_for(tmp_path, provider=None, **kwargs):
    return create_app(Settings(_env_file=None, senamhi_enabled=False, data_dir=tmp_path, iot_key=KEY, **kwargs),
                      vision_provider=provider)


def upload(client, color='blue', camera='chillon-01'):
    response = client.post(f'/api/iot/upload?camera_id={camera}', content=photo(color),
                           headers={'Content-Type': 'image/jpeg', 'X-IoT-Key': KEY})
    assert response.status_code == 201, response.text
    return response.json()


def test_disabled_keeps_original_without_fake_results_or_engine_import(tmp_path):
    with TestClient(app_for(tmp_path)) as client:
        frame = upload(client)
        result = client.get('/api/analyses/' + frame['id']).json()
        assert result['status'] == 'not_configured'
        assert result['result'] is None and result['overlay_url'] is None
        assert result['water_fraction'] is None and result['candidate_count'] is None
        assert result['frame_id'] == frame['id'] and not result['objects_available']
        assert client.get(result['original_url']).status_code == 200
        assert client.get(result['report_url']).status_code == 200
        assert 'app.vision.waki_ia' not in sys.modules
        html = client.get('/').text
        assert 'Ver informe IA' in html and 'CAM-01 • Frontal' not in html
        assert 'Actualizado hace 2 min' not in html and 'Infrarrojo / Nocturna' not in html


def test_capture_overlay_and_report_remain_associated_and_citizens_separate(tmp_path):
    provider = FakeVision()
    with TestClient(app_for(tmp_path, provider)) as client:
        frame = upload(client)
        second = upload(client, 'red')
        result = client.get('/api/analyses/' + frame['id']).json()
        assert result['status'] == 'analyzed' and result['candidate_count'] == 1
        assert result['water_fraction'] == .25 and result['objects_available']
        assert result['frame_id'] == frame['id']
        original = client.get(result['original_url']).content
        overlay = client.get(result['overlay_url'])
        assert overlay.content != original and overlay.headers['content-type'] == 'image/jpeg'
        assert provider.calls[0][0] == original
        assert provider.calls[0][1]['point_id'] == frame['id']
        assert provider.calls[0][1]['captured_at'] is None
        assert client.get('/api/cameras/chillon-01/latest').json()['latest']['id'] == second['id']
        html = client.get(result['report_url']).text
        assert 'Botella de plástico' in html and 'OBJ-001' in html and 'ZONA-001' in html
        assert 'Reportes ciudadanos' not in html and 'pendientes de revisión humana' in html
        popup = client.get(result['report_url'] + '/contenido')
        assert popup.status_code == 200 and popup.headers['cache-control'] == 'no-store'
        assert 'Botella de plástico' in popup.text and frame['id'] in popup.text
        assert '<html' not in popup.text and '<script' not in popup.text
        assert 'Volver a las imágenes' not in popup.text
        download = client.get(f"/api/analyses/{frame['id']}/report.json")
        assert 'attachment' in download.headers['content-disposition']
        assert download.json()['frame_id'] == frame['id']
        assert client.get('/api/reports').json()['total'] == 0
        history = client.get('/api/cameras/chillon-01/analyses?limit=1').json()
        assert history['total'] == 2 and history['items'][0]['id'] == second['id']
        assert history['items'][0]['result'] is None
        assert client.get('/api/cameras/chillon-01/analyses?limit=1&offset=1').json()['items'][0]['id'] == frame['id']
        assert client.get('/api/cameras/rimac-01/analyses').json()['items'] == []


@pytest.mark.parametrize('water,objects,empty,status,count,ratio', [
    (True, False, False, 'partial', None, .25),
    (False, True, False, 'partial', 1, None),
    (False, False, False, 'error', None, None),
    (True, True, True, 'analyzed', 0, 0.0),
])
def test_partial_errors_and_empty_are_not_fabricated(tmp_path, water, objects, empty, status, count, ratio):
    with TestClient(app_for(tmp_path, FakeVision(water=water, objects=objects, empty=empty))) as client:
        frame = upload(client)
        result = client.get('/api/analyses/' + frame['id']).json()
        assert result['status'] == status and result['candidate_count'] == count
        assert result['water_fraction'] == ratio
        assert (result['overlay_url'] is None) == (status == 'error')
        assert client.get(result['report_url']).status_code == 200


def test_model_failure_does_not_lose_upload_and_retry_is_authenticated(tmp_path):
    provider = FakeVision(fail=True)
    with TestClient(app_for(tmp_path, provider)) as client:
        frame = upload(client)
        path = '/api/analyses/' + frame['id']
        result = client.get(path).json()
        assert result['status'] == 'error' and result['result'] is None
        assert 'Private' not in json.dumps(result)
        assert client.get(frame['image_url']).status_code == 200
        assert client.post(path + '/retry').status_code == 401
        provider.fail = False
        assert client.post(path + '/retry', headers={'X-IoT-Key': KEY}).status_code == 202
        assert client.get(path).json()['status'] == 'analyzed'
        assert len(provider.calls) == 2
        assert client.post(path + '/retry', headers={'X-IoT-Key': KEY}).status_code == 409


def test_snapshot_survives_camera_retention_and_analysis_retention_is_bounded(tmp_path):
    with TestClient(app_for(tmp_path, FakeVision(), iot_retention_images=1, ai_retention_images=2)) as client:
        first = upload(client)
        result = client.get('/api/analyses/' + first['id']).json()
        upload(client, 'red')
        assert client.get(first['image_url']).status_code == 404
        assert client.get(result['original_url']).status_code == 200
        assert client.get(result['overlay_url']).status_code == 200
        upload(client, 'green')
        assert client.get(result['report_url']).status_code == 404
        assert not (tmp_path / 'analyses' / UUID(first['id']).hex).exists()
        assert client.get('/api/cameras/chillon-01/analyses').json()['total'] == 2


def test_restart_marks_interrupted_and_preserves_finished_results(tmp_path):
    application = app_for(tmp_path, FakeVision())
    with TestClient(application) as client:
        frame = upload(client)
        processing = application.state.processing
        job = uuid4().hex
        processing.enqueue({'id': job, 'camera_id': 'chillon-01', 'received_at': '2026-01-01T00:00:00+00:00',
                            'captured_at': None}, 'chillon', photo())
        assert processing.repository.claim(job)
    with TestClient(app_for(tmp_path, FakeVision())) as client:
        interrupted = client.get('/api/analyses/' + job).json()
        assert interrupted['status'] == 'error' and 'reinició' in interrupted['message']
        assert client.get('/api/analyses/' + frame['id']).json()['status'] == 'analyzed'
        assert client.get(interrupted['original_url']).status_code == 200


def test_queue_is_bounded_and_same_job_cannot_be_claimed_twice(tmp_path):
    application = app_for(tmp_path, FakeVision(), ai_max_pending=1)
    with TestClient(application):
        processing = application.state.processing
        ids = [uuid4().hex, uuid4().hex]
        for job in ids:
            processing.enqueue({'id': job, 'camera_id': 'chillon-01', 'received_at': '2026-01-01T00:00:00+00:00',
                                'captured_at': None}, 'chillon', photo())
        assert processing.get(ids[0]).status == 'queued'
        assert processing.get(ids[1]).status == 'error'
        assert processing.repository.claim(ids[0])
        assert not processing.repository.claim(ids[0])


def test_invalid_identifiers_artifact_whitelist_and_pagination(tmp_path):
    with TestClient(app_for(tmp_path)) as client:
        assert client.get('/api/analyses/not-a-uuid').status_code == 422
        assert client.get('/api/analyses/' + str(uuid4())).status_code == 404
        assert client.get('/informes-ia/' + str(uuid4()) + '/contenido').status_code == 404
        assert client.get('/api/cameras/unknown/analyses').status_code == 404
        assert client.get('/api/cameras/chillon-01/analyses?limit=0').status_code == 422
        frame = upload(client)
        for kind in ('water_overlay', 'report.json', 'input.jpg', 'reporte.json'):
            assert client.get(f"/api/analyses/{frame['id']}/artifacts/{kind}").status_code == 404


def test_provider_checks_configuration_without_loading_model(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, model_provider='waki', ai_water_checkpoint=tmp_path)
    provider = WakiProvider(settings)
    assert 'río' in provider.configuration_issue('rimac')
    assert 'checkpoint' in provider.configuration_issue('chillon')
    assert provider.water is None and provider.dino is None
    for name in ('config.json', 'preprocessor_config.json', 'model.safetensors'):
        (tmp_path / name).touch()
    monkeypatch.setattr('app.vision.providers.waki.importlib.util.find_spec', lambda name: None)
    assert 'dependencias' in provider.configuration_issue('chillon')


def test_processing_state_and_http_queries_remain_available_during_inference(tmp_path):
    entered, release = threading.Event(), threading.Event()

    class BlockingVision(FakeVision):
        def analyze(self, image, context, output):
            entered.set()
            if not release.wait(timeout=5):
                raise TimeoutError('El test no liberó el detector.')
            return super().analyze(image, context, output)

    with TestClient(app_for(tmp_path, BlockingVision())) as client, ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(upload, client)
        try:
            assert entered.wait(timeout=3)
            history = client.get('/api/cameras/chillon-01/analyses').json()
            assert history['total'] == 1 and history['items'][0]['status'] == 'processing'
            assert history['items'][0]['overlay_url'] is None
            assert client.get(history['items'][0]['original_url']).status_code == 200
            assert client.get('/api/health').status_code == 200
        finally:
            release.set()
        frame = pending.result(timeout=5)
        assert client.get('/api/analyses/' + frame['id']).json()['status'] == 'analyzed'


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1, 1.1, True])
def test_invalid_water_ratios_are_rejected(value):
    result = {'analysis_mode': 'live_models', 'modules': {
        'water_segmentation': {'status': 'predicted_nonempty', 'fraction_of_image_predicted_as_water': value},
        'object_candidates': {},
    }}
    with pytest.raises(ValueError):
        ProcessingService.outcome(result)


def test_replay_is_never_accepted_as_a_new_detection():
    with pytest.raises(ValueError, match='reproducciones'):
        ProcessingService.outcome({'analysis_mode': 'offline_replay'})
