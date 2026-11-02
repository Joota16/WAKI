"""Verifica que YOLOE recibe recursos locales y reutiliza el motor preparado."""
import sys
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.vision.providers.local_yoloe import LocalYoloe


def test_missing_files_fail_before_importing_or_downloading_models(tmp_path):
    provider = LocalYoloe(tmp_path / 'missing.pt', None, 'cpu')
    with pytest.raises(FileNotFoundError, match='pesos'):
        provider.initialize()
    (tmp_path / 'model.pt').touch()
    provider = LocalYoloe(tmp_path / 'model.pt', tmp_path / 'missing.npz', 'cpu')
    with pytest.raises(FileNotFoundError, match='prompts'):
        provider.initialize()


@pytest.mark.parametrize('task,names,error', [
    ('segment', ['tire', 'plastic bottle'], None),
    ('detect', ['tire', 'plastic bottle'], 'segmentación'),
    ('segment', ['person'], 'clases'),
])
def test_prepared_embeddings_and_model_are_reused_without_text_encoder(tmp_path, monkeypatch, task, names, error):
    monkeypatch.setenv('YOLO_CONFIG_DIR', str(tmp_path / 'settings'))
    checkpoint, prompts = tmp_path / 'yoloe-26s-seg.pt', tmp_path / 'prompts.npz'
    checkpoint.touch(); prompts.touch()
    models, adapters = [], []

    class FakeModel:
        def __init__(self, path):
            assert path == str(checkpoint.resolve())
            self.task, self.names = task, {}
            models.append(self)

        def load_prompt_embeddings(self, path):
            assert path == str(prompts.resolve())
            self.names = dict(enumerate(names))

        def get_text_pe(self, classes):
            raise AssertionError('No se debe cargar un codificador de texto.')

    class FakeMultiscale:
        last_runtime_ms = 12

        def __init__(self, *, device, weights):
            assert device == 'cpu' and weights is models[0]
            adapters.append(self)

        def predict(self, image):
            return [{'label': 'tire', 'bbox_xyxy': [1, 2, 3, 4], 'score_uncalibrated': .5}]

    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(YOLOE=FakeModel))
    monkeypatch.setitem(sys.modules, 'app.vision.waki_ia.hybrid_report', SimpleNamespace(YoloeMultiscaleAdapter=FakeMultiscale))
    monkeypatch.setitem(sys.modules, 'app.vision.waki_ia.yoloe_multiscale', SimpleNamespace(DEFAULT_CLASSES=['tire', 'plastic bottle']))
    provider = LocalYoloe(checkpoint, prompts, 'cpu')
    if error:
        with pytest.raises(ValueError, match=error):
            provider.predict(object())
        assert provider.detector is None
        return
    assert provider.predict(object())[0]['label'] == 'tire'
    assert provider.predict(object())[0]['label'] == 'tire'
    assert len(models) == len(adapters) == 1
    assert provider.last_runtime_ms == 12
    assert adapters[0].source == 'yoloe-local'


def test_empty_optional_yoloe_paths_are_disabled():
    settings = Settings(_env_file=None, ai_yoloe_checkpoint='', ai_yoloe_prompts='')
    assert settings.ai_yoloe_checkpoint is None and settings.ai_yoloe_prompts is None
