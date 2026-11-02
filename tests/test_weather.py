import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import threading

from fastapi.testclient import TestClient
import httpx
import pytest

from app.config import Settings
from app.db.database import Database
from app.integrations.senamhi import InvalidStationData
from app.integrations.senamhi_weather import OBRAJILLO_WEATHER, WEATHER_STATIONS, SenamhiWeatherProvider, parse_daily_weather
from app.main import create_app
from app.repositories.weather import WeatherRepository
from app.schemas.weather import DailyWeather
from app.services.weather import WeatherService

FIXTURE = Path(__file__).parent / 'fixtures/senamhi-weather-obrajillo.html'
TODAY = date(2026, 10, 29)


def test_real_weather_preserves_zero_rain_missing_temperatures_and_old_dates():
    readings = parse_daily_weather(FIXTURE.read_text(), OBRAJILLO_WEATHER, today=TODAY)
    assert len(readings) == 31
    assert readings[-1] == DailyWeather(observed_date=date(2026, 9, 30), precipitation_mm=0)
    assert max(item.precipitation_mm for item in readings) == 1.5
    assert all(item.temperature_max_c is None and item.temperature_min_c is None for item in readings)
    assert sum(item.precipitation_mm is not None for item in readings) == 31
    assert OBRAJILLO_WEATHER.code == '156133' and OBRAJILLO_WEATHER.catalog_code == '111159'
    assert 'cod=111159' in OBRAJILLO_WEATHER.source_url
    assert {station.name for station in WEATHER_STATIONS.values()} == {'Obrajillo'}


@pytest.mark.parametrize('old,new', [
    ('ESTACIÓN: OBRAJILLO', 'ESTACIÓN: PUENTE MAGDALENA'),
    ('Código: 156133', 'Código: 111151'), ('Meteorológica', 'Hidrológica'),
    ('(mm/día)', '(cm/día)'), ("valueSuffix: '°C'", "valueSuffix: '°F'"),
    ("name: 'Precipitación'", "name: 'Nivel'"),
    ('data: [0,0,0', 'data: calculate([0,0,0'),
    ('data: [0,0,0', 'data: [-1,0,0'),
    ('data: [0,0,0', 'data: [NaN,0,0'),
    ('data: [0,0,0', 'data: [true,0,0'),
    ('data: [0,0,0', 'data: [0,0'),
    ('"2026-09-30"', '"2099-09-30"'), ('"2026-09-30"', '"2026-09-29"'),
])
def test_changed_source_is_rejected_without_inventing_weather(old, new):
    html = FIXTURE.read_text()
    assert old in html
    with pytest.raises(InvalidStationData):
        parse_daily_weather(html.replace(old, new), OBRAJILLO_WEATHER, today=TODAY)


def test_temperature_is_supported_only_when_source_publishes_it_and_null_rain_is_missing():
    html = FIXTURE.read_text().replace('data: [0,0,0', 'data: [null,0,0')
    html = html.replace('data: [null,null,null', 'data: [20.5,null,null', 1)
    # La segunda serie, que sigue vacía en la muestra original, recibe un valor de prueba.
    html = html.replace('data: [null,null,null', 'data: [-3.1,null,null', 1)
    reading = parse_daily_weather(html, OBRAJILLO_WEATHER, today=TODAY)[0]
    assert reading.precipitation_mm is None
    assert reading.temperature_max_c == 20.5 and reading.temperature_min_c == -3.1


def test_public_provider_uses_catalog_url_not_displayed_code_or_protected_table(monkeypatch):
    import app.integrations.senamhi_weather as adapter
    original = adapter.parse_daily_weather
    monkeypatch.setattr(adapter, 'parse_daily_weather', lambda html, station: original(html, station, today=TODAY))
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, headers={'content-type': 'text/html'}, text=FIXTURE.read_text())

    readings = asyncio.run(SenamhiWeatherProvider(httpx.MockTransport(respond)).fetch(OBRAJILLO_WEATHER))
    assert readings[-1].precipitation_mm == 0
    assert len(requests) == 1 and requests[0].method == 'GET'
    assert requests[0].url.params['cod'] == '111159'
    transport = httpx.MockTransport(lambda request: httpx.Response(200, headers={'content-type': 'text/html'}, text='Verify you are human'))
    with pytest.raises(InvalidStationData):
        asyncio.run(SenamhiWeatherProvider(transport).fetch(OBRAJILLO_WEATHER))


class FakeWeatherProvider:
    def __init__(self, readings=None):
        self.readings, self.calls, self.error = readings or [], 0, None

    async def fetch(self, station):
        self.calls += 1
        if self.error: raise self.error
        return self.readings


def test_weather_sync_corrections_missing_values_failure_and_restart(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    db = Database(settings.database_path)
    db.initialize()
    provider = FakeWeatherProvider(parse_daily_weather(FIXTURE.read_text(), OBRAJILLO_WEATHER, today=TODAY))
    service = WeatherService(WeatherRepository(db), provider, settings)
    asyncio.run(service.refresh())
    snapshot = service.get('chillon')
    assert snapshot.status == 'stale'
    assert snapshot.latest_precipitation.value == 0 and snapshot.latest_precipitation.observed_date == date(2026, 9, 30)
    assert snapshot.latest_temperature_max is None and snapshot.latest_temperature_min is None
    provider.readings[-1].precipitation_mm = 2.5
    asyncio.run(service.refresh())
    updated = service.get('chillon')
    assert updated.latest_precipitation.value == 2.5 and len(updated.readings) == 31
    provider.error = TimeoutError('private error details')
    asyncio.run(service.refresh())
    failed = service.get('chillon')
    assert failed.source_error and failed.status == 'error'
    assert failed.latest_precipitation == updated.latest_precipitation
    assert failed.last_success_at == updated.last_success_at
    assert 'private error details' not in failed.model_dump_json()
    db.initialize()
    restored = WeatherService(WeatherRepository(db), FakeWeatherProvider(), settings)
    assert restored.get('chillon').model_dump() == failed.model_dump()
    provider.error = None
    asyncio.run(service.refresh())
    assert not service.get('chillon').source_error


def test_latest_date_is_separate_for_each_metric_and_zero_temperature_is_valid(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    db = Database(settings.database_path)
    db.initialize()
    today = datetime.now(timezone.utc).date()
    provider = FakeWeatherProvider([
        DailyWeather(observed_date=today - timedelta(days=2), temperature_max_c=0, temperature_min_c=-2),
        DailyWeather(observed_date=today - timedelta(days=1), precipitation_mm=0),
    ])
    service = WeatherService(WeatherRepository(db), provider, settings)
    asyncio.run(service.refresh())
    snapshot = service.get('chillon')
    assert snapshot.status == 'ok'
    assert snapshot.latest_temperature_max.value == 0
    assert snapshot.latest_temperature_max.observed_date == today - timedelta(days=2)
    assert snapshot.latest_precipitation.observed_date == today - timedelta(days=1)


def test_weather_api_reads_cache_only_and_never_duplicates_magdalena(tmp_path):
    provider = FakeWeatherProvider()
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False), weather_provider=provider)
    with TestClient(app) as client:
        for _ in range(3):
            response = client.get('/api/hydrology/chillon/weather')
            assert response.headers['cache-control'] == 'no-store'
            data = response.json()
            assert data['station']['code'] == '156133'
            assert data['status'] == 'disabled' and data['latest_precipitation'] is None
            assert data['latest_temperature_max'] is None and data['latest_temperature_min'] is None
        rimac = client.get('/api/hydrology/rimac/weather').json()
        assert rimac['status'] == 'not_configured' and rimac['station'] is None and rimac['readings'] == []
        assert client.get('/api/hydrology/inventado/weather').status_code == 422
        html = client.get('/').text
        assert html.count('data-weather-station=') == 1
        assert 'data-weather-station="156133"' in html and 'data-weather-station="111151"' not in html
        assert html.count('data-discharge-station=') == 2
        assert 'water-level-card' in html and 'Últimos reportes ciudadanos' in html
        assert provider.calls == 0


def test_weather_polling_is_nonblocking_and_cancelled_at_shutdown(tmp_path):
    started, cancelled = threading.Event(), threading.Event()

    class WaitingWeatherProvider:
        async def fetch(self, station):
            started.set()
            try: await asyncio.sleep(3600)
            finally: cancelled.set()

    class UnusedProvider:
        async def fetch(self, station): raise TimeoutError('simulated source unavailable')

    app = create_app(Settings(_env_file=None, data_dir=tmp_path), weather_provider=WaitingWeatherProvider(),
                     hydrology_provider=UnusedProvider(), discharge_provider=UnusedProvider())
    with TestClient(app) as client:
        assert started.wait(timeout=2)
        assert client.get('/api/health').status_code == 200
        assert client.get('/api/hydrology/chillon/weather').json()['status'] == 'loading'
    assert cancelled.wait(timeout=2)
