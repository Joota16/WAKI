from datetime import datetime

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from test_accounts_and_moderation import client, settings, csrf, login, register, review, alert_values
from test_reports import payload, send

POINT = {'name': 'Puente de prueba · margen del río', 'latitude': -11.8924, 'longitude': -77.0682}


def configure(client, **changes):
    return client.put('/api/admin/alerts/points/chillon-01', json={**POINT, **changes}, headers=csrf(client))


def guided(**changes):
    return {'kind': 'inundacion', 'source_type': 'camera', 'source_id': 'chillon-01', 'message_key': 'stay_clear', **changes}


def publish(client, **changes):
    return client.post('/api/alerts', json=guided(**changes), headers=csrf(client))


def test_admin_sources_use_malecon_chillon_and_only_list_validated_reports(client):
    pending = send(client).json()
    located = send(client).json()
    unlocated = send(client, payload(latitude=None, longitude=None, accuracy_m=None)).json()
    login(client)
    review(client, located, 'validated', 'Comentario de revisión privado')
    review(client, unlocated, 'validated')
    data = client.get('/api/admin/alerts/options').json()
    assert [item['id'] for item in data['kinds']] == ['inundacion', 'derrumbe', 'erosion_fluvial']
    assert [item['source_id'] for item in data['cameras']] == ['chillon-01']
    camera = data['cameras'][0]
    assert camera['configured'] and camera['name'] == 'Malecón Chillón'
    assert camera['latitude'] == -11.913546150295304
    assert camera['longitude'] == -77.07124450899127
    assert {item['source_id'] for item in data['reports']} == {located['id'], unlocated['id']}
    assert pending['id'] not in str(data) and 'Comentario de revisión privado' not in str(data)
    assert next(item for item in data['reports'] if item['source_id'] == unlocated['id'])['configured'] is False
    assert client.get('/api/cameras/chillon-01/latest').json()['latest'] is None
    alert = publish(client)
    assert alert.status_code == 201
    assert alert.json()['location'] == 'Malecón Chillón'
    assert alert.json()['latitude'] == camera['latitude']
    assert publish(client, source_id='rimac-01').status_code == 422
    assert configure(client).status_code == 200
    updated = client.get('/api/admin/alerts/options?limit=1').json()
    assert updated['total_reports'] == 2 and len(updated['reports']) == 1
    assert updated['cameras'][0]['name'] == POINT['name'] and updated['cameras'][0]['configured']


def test_guided_notice_uses_server_title_template_and_named_point_and_keeps_snapshot(client):
    login(client); configure(client)
    result = publish(client)
    assert result.status_code == 201, result.text
    alert = result.json()
    assert alert['title'] == 'Inundación' and alert['location'] == POINT['name']
    assert alert['source_type'] == 'camera' and alert['latitude'] == POINT['latitude']
    assert alert['message'] == 'Mantente alejado del área afectada y sigue las indicaciones de las autoridades.'
    assert configure(client, name='Otro lugar de prueba', latitude=-12).status_code == 200
    # La edición del punto no reescribe el lugar ni el mensaje de un aviso anterior.
    saved = client.get('/api/alerts').json()['items'][0]
    assert saved == alert
    history = client.get('/api/admin/alerts/history').json()['items'][0]
    assert history['published_by'] == 'admin' and history['closed_by'] is None
    assert datetime.fromisoformat(history['created_at']).utcoffset().total_seconds() == 0
    guest = TestClient(client.app)
    try:
        public = guest.get('/api/alerts').json()['items'][0]
        assert 'published_by' not in public and 'closed_by' not in public
        assert public['longitude'] == POINT['longitude']
    finally:
        guest.close()


@pytest.mark.parametrize('changes', [
    {'source_id': 'unknown-camera'}, {'source_type': 'fake'}, {'message_key': 'invented'},
    {'latitude': 10}, {'title': 'Texto libre'}, {'message': 'Texto libre'}, {'location': 'Ubicación inventada'},
    {'kind': 'huaico'}, {'kind': 'otro'},
])
def test_invalid_or_forged_guided_notice_is_not_published(client, changes):
    login(client); configure(client)
    assert publish(client, **changes).status_code == 422
    assert client.get('/api/alerts').json()['items'] == []


@pytest.mark.parametrize('radius', [0, -30, 10001, 2.5, None, 'not-a-number'])
def test_invalid_danger_radius_is_not_published(client, radius):
    login(client)
    assert publish(client, radius_m=radius).status_code == 422
    assert client.get('/api/alerts').json()['items'] == []


def test_danger_radius_is_public_traceable_and_preserved_after_close_and_restart(settings):
    with TestClient(create_app(settings)) as instance:
        login(instance)
        created = publish(instance, kind='erosion_fluvial', radius_m=30)
        assert created.status_code == 201, created.text
        alert = created.json()
        assert alert['title'] == 'Erosión fluvial' and alert['radius_m'] == 30
        assert alert['location'] == 'Malecón Chillón'
        guest = TestClient(instance.app)
        try:
            public = guest.get('/api/alerts').json()['items'][0]
            assert public['radius_m'] == 30 and public['latitude'] == alert['latitude']
            assert public['longitude'] == alert['longitude'] and 'published_by' not in public
        finally:
            guest.close()
        events = instance.app.state.alerts.events(0)
        assert events[-1]['data']['radius_m'] == 30
        large = publish(instance, radius_m=75).json()
        assert large['radius_m'] == 75
        closed = instance.post('/api/alerts/' + alert['id'] + '/close', headers=csrf(instance)).json()
        assert not closed['active'] and closed['radius_m'] == 30
    with TestClient(create_app(settings)) as instance:
        login(instance)
        history = instance.get('/api/admin/alerts/history?status=closed').json()['items']
        assert len(history) == 1 and history[0]['id'] == alert['id'] and history[0]['radius_m'] == 30
        active = instance.get('/api/alerts').json()['items']
        assert len(active) == 1 and active[0]['id'] == large['id'] and active[0]['radius_m'] == 75


def test_report_source_is_revalidated_at_publication_and_location_is_not_invented(client):
    located = send(client).json()
    no_gps = send(client, payload(latitude=None, longitude=None, accuracy_m=None)).json()
    login(client)
    assert publish(client, source_type='report', source_id=located['id']).status_code == 422
    located = review(client, located, 'validated').json()
    review(client, no_gps, 'validated')
    assert publish(client, source_type='report', source_id=no_gps['id']).status_code == 422
    assert publish(client, source_type='report', source_id='not-a-uuid').status_code == 422
    result = publish(client, source_type='report', source_id=located['id'], kind='erosion_fluvial', message_key='avoid_travel')
    assert result.status_code == 201, result.text
    assert result.json()['title'] == 'Erosión fluvial'
    assert result.json()['location'] == f"Ubicación del reporte validado {located['id'][:8]}"
    assert result.json()['latitude'] == located['latitude']
    review(client, located, 'discarded')
    assert publish(client, source_type='report', source_id=located['id']).status_code == 422
    # La publicación histórica conserva el punto que tenía al emitirse.
    assert client.get('/api/admin/alerts/history').json()['items'][0]['latitude'] == located['latitude']


def test_nearby_named_reference_does_not_move_the_report_marker(client):
    report = send(client, payload(latitude=-11.8925)).json()
    login(client); configure(client); review(client, report, 'validated')
    result = publish(client, source_type='report', source_id=report['id']).json()
    assert result['location'].startswith('Cerca de ' + POINT['name'])
    assert result['latitude'] == -11.8925
    assert result['latitude'] != POINT['latitude']


def test_repository_rechecks_validated_source_in_same_transaction(client, monkeypatch):
    report = send(client).json(); login(client)
    report = review(client, report, 'validated').json()
    service = client.app.state.alerts
    resolve = service.resolve_source
    def changed_source(*args):
        source = resolve(*args)
        with client.app.state.database.connect() as db:
            db.execute("UPDATE reports SET review_status='pending' WHERE id=?", (report['id'],))
        return source
    monkeypatch.setattr(service, 'resolve_source', changed_source)
    assert publish(client, source_type='report', source_id=report['id']).status_code == 422
    assert client.get('/api/alerts').json()['items'] == []


def test_history_filters_pagination_and_idempotent_close(client):
    login(client); configure(client)
    first = publish(client).json()
    second = publish(client, kind='derrumbe', message_key='official_updates').json()
    assert client.post('/api/alerts/' + first['id'] + '/close', headers=csrf(client)).status_code == 200
    closed = client.get('/api/admin/alerts/history?status=closed').json()
    assert closed['total'] == 1 and closed['items'][0]['id'] == first['id']
    assert closed['items'][0]['closed_by'] == 'admin' and closed['items'][0]['closed_at']
    client.post('/api/alerts/' + first['id'] + '/close', headers=csrf(client))
    assert client.get('/api/admin/alerts/history?status=closed').json() == closed
    active = client.get('/api/admin/alerts/history?status=active').json()
    assert active['total'] == 1 and active['items'][0]['id'] == second['id']
    page = client.get('/api/admin/alerts/history?limit=1&offset=1').json()
    assert page['total'] == 2 and len(page['items']) == 1
    assert client.get('/api/admin/alerts/history?status=invalid').status_code == 422
    assert client.get('/api/admin/alerts/options?limit=51').status_code == 422
    assert client.get('/api/admin/alerts/history?offset=-1').status_code == 422


def test_admin_only_options_points_and_history(client):
    for path in ['/api/admin/alerts/options', '/api/admin/alerts/history']:
        assert client.get(path).status_code == 401
    assert client.put('/api/admin/alerts/points/chillon-01', json=POINT).status_code == 401
    register(client)
    for path in ['/api/admin/alerts/options', '/api/admin/alerts/history']:
        assert client.get(path).status_code == 403
    assert configure(client).status_code == 403
    login(client)
    assert client.put('/api/admin/alerts/points/chillon-01', json=POINT).status_code == 403
    assert client.put('/api/admin/alerts/points/chillon-01', json=POINT,
                      headers={**csrf(client), 'Origin': 'https://invalid.example'}).status_code == 403
    assert configure(client, latitude=91).status_code == 422
    assert configure(client, longitude=181).status_code == 422
    assert client.put('/api/admin/alerts/points/chillon-01',
                      content='{"name":"Punto de prueba","latitude":-11,"longitude":NaN}',
                      headers={**csrf(client), 'Content-Type': 'application/json'}).status_code == 422


def test_legacy_alerts_and_new_sources_survive_schema_migration_and_restart(settings):
    with TestClient(create_app(settings)) as instance:
        login(instance)
        legacy = instance.post('/api/alerts', json=alert_values(), headers=csrf(instance)).json()
        database = instance.app.state.database
    with database.connect() as db:
        db.execute("UPDATE alerts SET kind='huaico',title='Huaico histórico' WHERE id=?", (legacy['id'],))
        for name in ['source_type', 'source_id', 'latitude', 'longitude', 'message_key', 'radius_m']:
            db.execute(f'ALTER TABLE alerts DROP COLUMN {name}')
    with TestClient(create_app(settings)) as instance:
        login(instance)
        assert instance.get('/api/admin/alerts/history').json()['items'][0]['id'] == legacy['id']
        assert instance.get('/api/alerts').json()['items'][0]['source_type'] is None
        historical = instance.get('/api/alerts').json()['items'][0]
        assert historical['kind'] == 'huaico' and historical['title'] == 'Huaico histórico'
        assert historical['radius_m'] is None
        configure(instance)
        new = publish(instance).json()
        instance.post('/api/alerts/' + new['id'] + '/close', headers=csrf(instance))
    with TestClient(create_app(settings)) as instance:
        login(instance)
        history = instance.get('/api/admin/alerts/history').json()
        assert history['total'] == 2
        saved = next(item for item in history['items'] if item['id'] == new['id'])
        assert not saved['active'] and saved['closed_at'] and saved['latitude'] == POINT['latitude']
        assert instance.get('/api/admin/alerts/options').json()['cameras'][0]['configured']
        with instance.app.state.database.connect() as db:
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
