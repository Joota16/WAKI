import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import threading
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
import httpx
import pytest

from app.config import Settings
from app.db.database import Database
from app.integrations.senamhi import InvalidStationData, MAGDALENA, SenamhiProvider, parse_daily_levels
from app.main import create_app
from app.repositories.hydrology import HydrologyRepository
from app.schemas.hydrology import DailyLevel
from app.schemas.hydrology import DischargeBatch
from app.services.hydrology import HydrologyService

FIXTURE = Path(__file__).parent / 'fixtures/senamhi-magdalena-chart.html'


def test_parse_recorded_public_chart():
    readings = parse_daily_levels(FIXTURE.read_text(), MAGDALENA, today=date(2026, 10, 29))
    assert len(readings) == 31
    assert readings[0] == DailyLevel(observed_date=date(2026, 9, 28), level_m=1.338)
    assert readings[-1] == DailyLevel(observed_date=date(2026, 10, 28), level_m=1.345)


@pytest.mark.parametrize('old,new', [
    ('111151', '202802'), ('PUENTE MAGDALENA', 'OTRA ESTACION'),
    ('Nivel promedio diario (m)', 'Caudal (m3/s)'),
    ('var datosNivel', 'var nuevaSerie'), ('"2026-10-28"', '"2099-10-28"'),
    ('"2026-10-28"', '"2026-10-27"'), ('1.345];', 'NaN];'),
    ('1.345];', 'true];'), ('1.345];', '];'),
    ('1.345];', '1.345].map(convertUnits);'),
])
def test_rejects_source_changes_instead_of_inventing_levels(old, new):
    original = FIXTURE.read_text()
    assert old in original
    with pytest.raises(InvalidStationData):
        parse_daily_levels(original.replace(old, new), MAGDALENA, today=date(2026, 10, 29))


def test_null_is_not_zero_and_scripts_are_never_executed():
    html = FIXTURE.read_text().replace('1.345];', 'null];')
    readings = parse_daily_levels(html, MAGDALENA, today=date(2026, 10, 29))
    assert readings[-1].level_m is None
    html = FIXTURE.read_text().replace('var datosNivel = [', 'var datosNivel = dangerousCode([')
    with pytest.raises(InvalidStationData):
        parse_daily_levels(html, MAGDALENA, today=date(2026, 10, 29))


def test_provider_http_uses_public_graph_and_rejects_captcha_pages(monkeypatch):
    import app.integrations.senamhi as adapter
    parser = adapter.parse_daily_levels
    monkeypatch.setattr(adapter, 'parse_daily_levels', lambda html, station: parser(html, station, today=date(2026, 10, 29)))
    requests = []

    def respond(request):
        requests.append(str(request.url))
        return httpx.Response(200, headers={'content-type': 'text/html; charset=UTF-8'}, text=FIXTURE.read_text())

    readings = asyncio.run(SenamhiProvider(httpx.MockTransport(respond)).fetch(MAGDALENA))
    assert readings[-1].level_m == 1.345
    assert requests == [MAGDALENA.source_url]
    for status, body in [(503, 'unavailable'), (200, '<html>Verify you are human</html>')]:
        transport = httpx.MockTransport(lambda request: httpx.Response(status, headers={'content-type': 'text/html'}, text=body))
        with pytest.raises((httpx.HTTPStatusError, InvalidStationData)):
            asyncio.run(SenamhiProvider(transport).fetch(MAGDALENA))


class FakeProvider:
    def __init__(self, readings=None):
        self.calls = 0
        self.readings = readings or []
        self.error = None

    async def fetch(self, station):
        self.calls += 1
        if self.error:
            raise self.error
        return self.readings


def recent_readings():
    today = datetime.now(ZoneInfo('America/Lima')).date()
    return [DailyLevel(observed_date=today - timedelta(days=2), level_m=1.355),
            DailyLevel(observed_date=today - timedelta(days=1), level_m=1.345)]


def test_sync_upserts_corrections_and_preserves_cache_on_failures_and_restart(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    db = Database(settings.database_path)
    db.initialize()
    repository = HydrologyRepository(db)
    provider = FakeProvider(recent_readings())
    service = HydrologyService(repository, provider, settings)
    asyncio.run(service.refresh())
    snapshot = service.get('chillon')
    assert snapshot.status == 'ok' and snapshot.previous_day_change_m == -.01
    assert snapshot.station == MAGDALENA and snapshot.last_success_at
    provider.readings[-1].level_m = 1.34
    asyncio.run(service.refresh())
    snapshot = service.get('chillon')
    assert len(snapshot.readings) == 2 and snapshot.latest.level_m == 1.34
    success = snapshot.last_success_at
    provider.error = TimeoutError('simulated private error')
    asyncio.run(service.refresh())
    snapshot = service.get('chillon')
    assert snapshot.status == 'error' and snapshot.source_error
    assert snapshot.latest.level_m == 1.34 and snapshot.last_success_at == success
    assert 'simulated private error' not in snapshot.model_dump_json()
    db.initialize()  # Reiniciar no borra reportes ni lecturas.
    restored = HydrologyService(HydrologyRepository(db), FakeProvider(), settings)
    assert restored.get('chillon').model_dump() == snapshot.model_dump()
    provider.error = None
    asyncio.run(service.refresh())
    assert not service.get('chillon').source_error


def test_missing_days_nulls_and_old_values_are_explicit(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    db = Database(settings.database_path)
    db.initialize()
    provider = FakeProvider([DailyLevel(observed_date=date(2020, 1, 1), level_m=0),
                             DailyLevel(observed_date=date(2020, 1, 3), level_m=1)])
    service = HydrologyService(HydrologyRepository(db), provider, settings)
    asyncio.run(service.refresh())
    snapshot = service.get('chillon')
    assert snapshot.status == 'stale' and snapshot.previous_day_change_m is None
    assert snapshot.readings[0].level_m == 0  # Un cero publicado sí es un valor válido.
    provider.readings = [DailyLevel(observed_date=date(2020, 1, 1)), DailyLevel(observed_date=date(2020, 1, 3))]
    asyncio.run(service.refresh())
    assert service.get('chillon').latest is None
    assert service.get('chillon').status == 'error'


def test_api_reads_only_cache_and_never_assigns_magdalena_to_rimac(tmp_path):
    provider = FakeProvider()
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False), hydrology_provider=provider)
    with TestClient(app) as client:
        assert client.get('/api/hydrology/chillon').json()['status'] == 'disabled'
        now = datetime.now(timezone.utc).isoformat()
        app.state.hydrology.repository.save(MAGDALENA.code, recent_readings(), now, now)
        for _ in range(3):
            response = client.get('/api/hydrology/chillon')
            assert response.headers['cache-control'] == 'no-store'
            data = response.json()
            assert data['station']['name'] == 'Puente Magdalena'
            assert data['latest']['level_m'] == 1.345
            assert data['metric'] == 'daily_mean_water_level'
        rimac = client.get('/api/hydrology/rimac').json()
        assert rimac['status'] == 'not_configured' and rimac['latest'] is None and rimac['station'] is None
        assert rimac['readings'] == []
        assert client.get('/api/hydrology/inventado').status_code == 422
        assert client.post('/api/hydrology/chillon').status_code == 405
        assert provider.calls == 0


def test_lifespan_polls_without_blocking_requests_and_cancels_on_shutdown(tmp_path):
    started, cancelled = threading.Event(), threading.Event()

    class WaitingProvider:
        async def fetch(self, station):
            started.set()
            try:
                await asyncio.sleep(3600)
            finally:
                cancelled.set()

    class UnusedDischargeProvider:
        async def fetch(self, station):
            return DischargeBatch(readings=[], source_url=station.source_url)

    class UnusedWeatherProvider:
        async def fetch(self, station):
            return []

    app = create_app(Settings(_env_file=None, data_dir=tmp_path), hydrology_provider=WaitingProvider(),
                     discharge_provider=UnusedDischargeProvider(), weather_provider=UnusedWeatherProvider())
    with TestClient(app) as client:
        assert started.wait(timeout=2)
        assert client.get('/api/health').status_code == 200
        assert client.get('/api/hydrology/chillon').json()['status'] == 'loading'
    assert cancelled.wait(timeout=2)
