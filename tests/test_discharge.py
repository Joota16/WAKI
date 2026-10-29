import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs

from fastapi.testclient import TestClient
import httpx
import pytest

from app.config import Settings
from app.db.database import Database
from app.integrations.senamhi import InvalidStationData
from app.integrations.senamhi_discharge import (
    DISCHARGE_STATIONS, SenamhiDischargeProvider, chart_url_from_metadata, parse_discharge,
)
from app.main import create_app
from app.repositories.discharge import DischargeRepository
from app.schemas.hydrology import DischargeBatch, DischargeReading
from app.services.discharge import DischargeService

FIXTURES = Path(__file__).parent / 'fixtures'
NOW = datetime(2026, 10, 29, 16, tzinfo=timezone.utc)


def chart(station):
    return (FIXTURES / f'senamhi-discharge-{station.code}.html').read_text()


def metadata(station):
    document = json.loads((FIXTURES / 'senamhi-discharge-metadata.json').read_text())
    document['features'] = [item for item in document['features'] if item['id'].endswith('.' + station.code)]
    return document


@pytest.mark.parametrize('station,expected,count', [(DISCHARGE_STATIONS[0], 1.8949, 77), (DISCHARGE_STATIONS[1], 2.1542, 14)])
def test_real_charts_preserve_discharge_and_lima_clock_without_using_thresholds(station, expected, count):
    readings = parse_discharge(chart(station), station, now=NOW)
    assert len(readings) == count
    assert readings[-1].discharge_m3s == expected
    # 10:00 visible en SENAMHI = 15:00 UTC, no 05:00 de Lima.
    assert readings[-1].observed_at == datetime(2026, 10, 29, 15, tzinfo=timezone.utc)
    assert all(item.discharge_m3s < 10 for item in readings)  # No son los umbrales 15..55 m³/s.


@pytest.mark.parametrize('old,new', [
    ('"codEstacion":"111151"', '"codEstacion":"47E9F488"'),
    ('"nomEstacion":"PUENTE MAGDALENA"', '"nomEstacion":"OTRA"'),
    ('"variable":"CAUDAL"', '"variable":"NIVEL"'),
    ('"unidad":"m3\\/s"', '"unidad":"m"'),
    ('var data = ', 'var data = calculate('),
    ('\n                            var dataCSV', '.map(convertUnits)\nvar dataCSV'),
    ('2.7751000000000001', 'NaN'),
    ('2.7751000000000001', '-1'),
    ('1792994400000', '1792994400'),
])
def test_rejects_wrong_station_units_or_invalid_source(old, new):
    station = DISCHARGE_STATIONS[1]
    html = chart(station)
    assert old in html
    with pytest.raises(InvalidStationData):
        parse_discharge(html.replace(old, new), station, now=NOW)


def test_null_is_not_zero_and_future_readings_are_rejected():
    station = DISCHARGE_STATIONS[1]
    html = chart(station).replace('2.7751000000000001', 'null')
    assert parse_discharge(html, station, now=NOW)[0].discharge_m3s is None
    html = chart(station).replace('2.7751000000000001', '0')
    assert parse_discharge(html, station, now=NOW)[0].discharge_m3s == 0
    with pytest.raises(InvalidStationData):
        parse_discharge(chart(station), station, now=NOW - timedelta(days=1))


@pytest.mark.parametrize('station', DISCHARGE_STATIONS)
def test_public_provider_uses_latest_catalog_date_and_never_pins_screenshot_date(monkeypatch, station):
    import app.integrations.senamhi_discharge as adapter
    original = adapter.parse_discharge
    monkeypatch.setattr(adapter, 'parse_discharge', lambda html, selected: original(html, selected, now=NOW))
    calls = []

    def respond(request):
        calls.append(request)
        if request.url.host == 'idesep.senamhi.gob.pe':
            assert request.url.params['featureID'] == f'estaciones_monitoreo.{station.code}'
            return httpx.Response(200, json=metadata(station))
        assert request.method == 'GET'
        assert request.url.params['id'] == station.code
        assert request.url.params['fecha_hora'] == '2026-10-29 15:00:00'
        assert request.url.params['variable'] == 'CAUDAL'
        return httpx.Response(200, headers={'content-type': 'text/html'}, text=chart(station))

    batch = asyncio.run(SenamhiDischargeProvider(httpx.MockTransport(respond)).fetch(station))
    assert len(calls) == 2
    assert batch.readings[-1].observed_at.hour == 15
    assert 'id=' + station.code in batch.source_url
    doc = metadata(station)
    doc['features'][0]['properties']['fecha_hora'] = '2026-10-30T16:00:00Z'
    assert parse_qs(chart_url_from_metadata(doc, station).split('?', 1)[1])['fecha_hora'] == ['2026-10-30 16:00:00']


@pytest.mark.parametrize('failure', ['wrong_station', 'no_date', 'wrong_variable', 'wrong_basin'])
def test_catalog_must_identify_the_expected_station(failure):
    station = DISCHARGE_STATIONS[1]
    doc = metadata(station)
    feature = doc['features'][0]
    if failure == 'wrong_station': feature['id'] = 'estaciones_monitoreo.OTRA'
    elif failure == 'no_date': feature['properties']['fecha_hora'] = None
    elif failure == 'wrong_variable': feature['properties']['variable'] = 'N'
    else: feature['properties']['nom_cuenca'] = 'Otra cuenca'
    with pytest.raises(InvalidStationData): chart_url_from_metadata(doc, station)


class FakeDischargeProvider:
    def __init__(self):
        self.calls = []
        self.failures = set()
        self.values = {'47E9F488': 1.8949, '111151': 2.1542}

    async def fetch(self, station):
        self.calls.append(station.code)
        if station.code in self.failures:
            raise TimeoutError('private error details')
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        return DischargeBatch(source_url=station.source_url, readings=[
            DischargeReading(observed_at=now - timedelta(hours=1), discharge_m3s=self.values[station.code]),
        ])


def test_independent_failures_upserts_and_persistence_preserve_daily_levels(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    database = Database(settings.database_path)
    database.initialize()
    provider = FakeDischargeProvider()
    service = DischargeService(DischargeRepository(database), provider, settings)
    asyncio.run(service.refresh())
    before = service.get('chillon')
    assert [item.latest.discharge_m3s for item in before] == [1.8949, 2.1542]
    provider.failures.add('47E9F488')
    provider.values['111151'] = 2.3
    asyncio.run(service.refresh())
    after = service.get('chillon')
    assert after[0].source_error and after[0].latest == before[0].latest
    assert after[0].last_success_at == before[0].last_success_at
    assert after[1].status == 'ok' and after[1].latest.discharge_m3s == 2.3
    assert len(after[1].readings) == 1  # Corrección del mismo instante, sin duplicados.
    assert service.get('rimac') == []
    database.initialize()
    restored = DischargeService(DischargeRepository(database), provider, settings)
    assert [item.model_dump() for item in restored.get('chillon')] == [item.model_dump() for item in after]


def test_api_only_reads_sqlite_and_replaces_ai_block(tmp_path):
    provider = FakeDischargeProvider()
    application = create_app(Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False), discharge_provider=provider)
    with TestClient(application) as client:
        for _ in range(3):
            response = client.get('/api/hydrology/chillon/discharge')
            assert response.headers['cache-control'] == 'no-store'
            data = response.json()
            assert len(data) == 2 and all(item['status'] == 'disabled' for item in data)
            assert all(item['unit'] == 'm3/s' and item['latest'] is None for item in data)
        assert client.get('/api/hydrology/rimac/discharge').json() == []
        assert client.get('/api/hydrology/otro/discharge').status_code == 422
        html = client.get('/').text
        assert 'Análisis de IA' not in html and 'ai-analysis-block' not in html
        assert html.count('data-discharge-station=') == 2
        assert 'Últimos reportes ciudadanos' in html
        assert provider.calls == []


def test_polling_starts_without_blocking_and_stops_cleanly(tmp_path):
    started, cancelled = threading.Event(), threading.Event()

    class WaitingProvider:
        async def fetch(self, station):
            started.set()
            try: await asyncio.sleep(3600)
            finally: cancelled.set()

    class UnusedLevelProvider:
        async def fetch(self, station): raise TimeoutError('simulated')

    class UnusedWeatherProvider:
        async def fetch(self, station): return []

    app = create_app(Settings(_env_file=None, data_dir=tmp_path), discharge_provider=WaitingProvider(),
                     hydrology_provider=UnusedLevelProvider(), weather_provider=UnusedWeatherProvider())
    with TestClient(app) as client:
        assert started.wait(timeout=2)
        assert client.get('/api/health').status_code == 200
        assert client.get('/api/hydrology/chillon/discharge').json()[0]['status'] == 'loading'
    assert cancelled.wait(timeout=2)
