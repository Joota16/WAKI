"""Comprueba la entrega de las páginas y sus recursos tras dividir los prototipos."""
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlparse

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app


class PageParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


@pytest.fixture
def client(tmp_path):
    application = create_app(Settings(_env_file=None, senamhi_enabled=False, data_dir=tmp_path, iot_key=""))
    with TestClient(application) as test_client:
        yield test_client


@pytest.mark.parametrize('path,expected_id,link', [
    ('/', 'map', '/reportar'),
    ('/reportar', 'citizenReportForm', '/'),
    ('/reportes', 'reports-empty', '/reportar'),
])
def test_pages_and_assets(client, path, expected_id, link):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    assert '{%' not in response.text
    page = PageParser(response.text)
    ids = [attrs['id'] for _, attrs in page.elements if 'id' in attrs]
    assert expected_id in ids
    assert len(ids) == len(set(ids)), 'Los fragmentos no deben duplicar identificadores.'
    assert any(tag == 'a' and urlparse(attrs.get('href', '')).path == link for tag, attrs in page.elements)
    if path == '/reportar':
        assert 'Simular ubicación' not in response.text
        assert '2 fotos de muestra' not in response.text
    elif path == '/':
        assert 'Estado del prototipo' not in response.text
    for tag, attrs in page.elements:
        assert not any(attr.startswith('on') or attr == 'style' for attr in attrs)
        assert tag != 'style'
        if tag == 'script':
            assert attrs.get('src'), 'El JavaScript debe estar en archivos separados.'
        asset = attrs.get('src') if tag == 'script' else attrs.get('href', '')
        if asset and urlparse(asset).path.startswith('/static/'):
            assert client.get(asset).status_code == 200, asset


def test_javascript_imports_are_served(client):
    static = Path(__file__).resolve().parent.parent / 'app' / 'static'
    for module in (static / 'js').rglob('*.js'):
        for relative in re.findall(r"from\s+['\"]([^'\"]+)['\"]", module.read_text()):
            target = (module.parent / relative).resolve()
            url = '/static/' + target.relative_to(static).as_posix()
            assert client.get(url).status_code == 200, f'{module.name}: {relative}'


def test_health_and_reserved_api_are_preserved(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'database': 'connected'}
    assert client.get('/api/reports').json()['items'] == []
    assert client.post('/api/iot/upload?camera_id=chillon-01').status_code == 503
