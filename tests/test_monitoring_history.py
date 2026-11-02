import asyncio
from datetime import date, datetime, timedelta, timezone
import json
import re

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.db.database import Database
from app.integrations.senamhi import _variable
from app.integrations.senamhi_discharge import DISCHARGE_STATIONS, parse_discharge
from app.main import create_app
from app.repositories.discharge import DischargeRepository
from app.schemas.hydrology import DailyLevel, DischargeBatch, DischargeReading, DischargeThresholds
from app.schemas.weather import DailyWeather
from app.services.discharge import DischargeService
from test_discharge import chart, NOW


def change_data(html, change):
    match = re.search(r'var data = (.*?)\n\s*var dataCSV', html, re.S)
    assert match
    data = json.loads(match.group(1))
    change(data)
    return html[:match.start(1)] + json.dumps(data) + html[match.end(1):]


@pytest.mark.parametrize('station,expected', [
    (DISCHARGE_STATIONS[0], (15, 20.72, 27.45)),
    (DISCHARGE_STATIONS[1], (27, 40, 55)),
])
def test_thresholds_are_taken_from_each_station_and_never_used_as_readings(station, expected):
    readings = parse_discharge(chart(station), station, now=NOW)
    assert tuple(readings[-1].thresholds.model_dump().values()) == expected
    assert readings[-1].threshold_level == 'below_yellow'
    assert readings[-1].discharge_m3s < expected[0]


@pytest.mark.parametrize('value,status', [(14.99, 'below_yellow'), (15, 'yellow'), (20.72, 'orange'), (27.45, 'red'), (0, 'below_yellow'), (None, None)])
def test_threshold_boundaries_and_missing_values(value, status):
    reading = DischargeReading(observed_at=NOW, discharge_m3s=value,
                               thresholds=DischargeThresholds(yellow_m3s=15, orange_m3s=20.72, red_m3s=27.45))
    assert reading.threshold_level == status
    assert DischargeReading(observed_at=NOW, discharge_m3s=value).threshold_level is None


@pytest.mark.parametrize('mutation', ['missing', 'string', 'negative', 'nan', 'unordered', 'duplicate', 'missing_date'])
def test_invalid_thresholds_do_not_discard_or_misclassify_valid_discharge(mutation):
    station = DISCHARGE_STATIONS[1]
    def change(data):
        if mutation == 'missing': data.pop('amarillo')
        elif mutation == 'missing_date': data['amarillo'].pop()
        elif mutation == 'duplicate': data['amarillo'].append(data['amarillo'][-1])
        else:
            data['amarillo'][-1][1] = {'string': '27', 'negative': -1, 'nan': float('nan'), 'unordered': 100}[mutation]
    readings = parse_discharge(change_data(chart(station), change), station, now=NOW)
    assert readings[-1].discharge_m3s == 2.1542
    assert readings[-1].thresholds is None and readings[-1].threshold_level is None


def test_thresholds_remain_attached_to_their_published_date():
    station = DISCHARGE_STATIONS[1]
    html = change_data(chart(station), lambda data: data['amarillo'][0].__setitem__(1, 28))
    readings = parse_discharge(html, station, now=NOW)
    assert readings[0].thresholds.yellow_m3s == 28
    assert readings[-1].thresholds.yellow_m3s == 27


def test_old_database_migrates_without_assigning_thresholds_to_old_measurements(tmp_path):
    database = Database(tmp_path / 'old.sqlite3')
    database.initialize()
    with database.connect() as db:
        db.execute('INSERT INTO discharge_readings(station_code,observed_at,discharge_m3s) VALUES (?,?,?)',
                   ('111151', NOW.isoformat(), 3))
        for name in ['yellow_m3s', 'orange_m3s', 'red_m3s']:
            db.execute('ALTER TABLE discharge_readings DROP COLUMN ' + name)
    database.initialize()
    database.initialize()
    _, rows = DischargeRepository(database).snapshot('111151')
    assert len(rows) == 1 and rows[0]['discharge_m3s'] == 3
    assert rows[0]['thresholds'] is None


def test_thresholds_persist_and_survive_source_failures(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    database = Database(settings.database_path)
    database.initialize()
    class Provider:
        fail = False
        async def fetch(self, station):
            if self.fail: raise TimeoutError()
            return DischargeBatch(source_url=station.source_url, readings=parse_discharge(chart(station), station, now=NOW))
    provider = Provider()
    service = DischargeService(DischargeRepository(database), provider, settings)
    asyncio.run(service.refresh())
    before = service.get('chillon')
    provider.fail = True
    asyncio.run(service.refresh())
    for previous, current in zip(before, service.get('chillon')):
        assert current.latest == previous.latest
        assert current.latest.thresholds is not None and current.source_error
    restored = DischargeService(DischargeRepository(database), provider, settings)
    assert restored.get('chillon')[1].latest.thresholds.red_m3s == 55


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False))) as client:
        now = datetime.now(timezone.utc)
        days = [DailyLevel(observed_date=date.today() - timedelta(days=index), level_m=None if index == 2 else index / 100)
                for index in range(65)]
        client.app.state.hydrology.repository.save('111151', days, now.isoformat(), now.isoformat())
        weather = [DailyWeather(observed_date=item.observed_date, precipitation_mm=0 if index == 0 else None,
                               temperature_max_c=20, temperature_min_c=None) for index, item in enumerate(days)]
        client.app.state.weather.repository.save('156133', weather, now.isoformat(), now.isoformat())
        for station in DISCHARGE_STATIONS:
            readings = [DischargeReading(observed_at=now - timedelta(hours=index), discharge_m3s=0 if index == 0 else 2,
                                         thresholds=DischargeThresholds(yellow_m3s=27, orange_m3s=40, red_m3s=55))
                        for index in range(100)]
            client.app.state.discharge.repository.save(station.code, DischargeBatch(readings=readings, source_url=station.source_url),
                                                       now.isoformat(), now.isoformat())
        yield client


@pytest.mark.parametrize('metric,station,total', [('level', '111151', 65), ('weather', '156133', 65), ('discharge', '111151', 100)])
def test_history_paginates_all_saved_records_beyond_chart_window(client, metric, station, total):
    path = f'/api/hydrology/chillon/history/{metric}?station_code={station}'
    response = client.get(path)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    first = response.json()
    assert first['total'] == total and len(first['items']) == 25
    assert first['station']['code'] == station
    second = client.get(path + '&offset=25').json()
    key = 'observed_at' if metric == 'discharge' else 'observed_date'
    assert first['items'][0][key] > first['items'][-1][key] > second['items'][0][key]
    assert len(client.get(path + '&limit=100').json()['items']) == total
    assert client.get(path + '&offset=200').json()['items'] == []
    if metric == 'weather':
        assert first['items'][0]['precipitation_mm'] == 0
        assert first['items'][1]['precipitation_mm'] is None
        assert 'thresholds' not in first['items'][0]
    elif metric == 'level':
        assert first['items'][0]['level_m'] == 0
        assert first['items'][2]['level_m'] is None
        assert 'thresholds' not in first['items'][0]
    else:
        assert first['items'][0]['discharge_m3s'] == 0
        assert first['items'][0]['thresholds']['red_m3s'] == 55
        assert first['items'][0]['threshold_level'] == 'below_yellow'


@pytest.mark.parametrize('path,status', [
    ('/api/hydrology/chillon/history/level?station_code=47E9F488', 404),
    ('/api/hydrology/rimac/history/discharge?station_code=111151', 404),
    ('/api/hydrology/chillon/history/weather?station_code=111151', 404),
    ('/api/hydrology/chillon/history/discharge', 404),
    ('/api/hydrology/chillon/history/other', 422),
    ('/api/hydrology/chillon/history/level?limit=101', 422),
    ('/api/hydrology/chillon/history/level?offset=-1', 422),
])
def test_history_station_binding_and_input_limits(client, path, status):
    assert client.get(path).status_code == status
