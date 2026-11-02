from datetime import datetime

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from test_accounts_and_moderation import ADMIN_PASSWORD, csrf, login, register, review
from test_reports import payload, send


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, senamhi_enabled=False, data_dir=tmp_path,
                    admin_username='admin', admin_password=ADMIN_PASSWORD)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as instance:
        yield instance


def assign(client, report, level, notes='Justificación privada de la evaluación'):
    return client.post('/api/reports/' + report['id'] + '/review', headers=csrf(client), json={
        'decision': 'validated', 'notes': notes, 'expected_version': report['review_version'],
        'attention_level': level,
    })


def snapshot(client):
    response = client.get('/api/attention/chillon')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    return response.json()


def test_pending_is_not_assumed_to_mean_monitoring_or_safety(client):
    result = snapshot(client)
    assert result['level'] is None and result['label'] == 'Pendiente de evaluación'
    assert result['evaluated_at'] is None and result['source_report_id'] is None
    report = send(client, payload(observed_condition='critico')).json()
    assert snapshot(client) == result
    assert report['attention_level'] is None
    html = client.get('/').text
    assert 'Nivel de atención' in html and 'Pendiente de evaluación' in html
    assert 'Nivel de riesgo' not in html and 'Riesgo Alto' not in html and '24 sep 2026' not in html


def test_validated_assignment_is_public_traceable_and_does_not_publish_alerts(client):
    report = send(client).json()
    login(client)
    response = assign(client, report, 'priority')
    assert response.status_code == 200, response.text
    updated = response.json()
    result = snapshot(client)
    assert result['level'] == updated['attention_level'] == 'priority'
    assert result['label'] == updated['attention_label'] == 'Atención prioritaria'
    assert result['evaluated_at'] == updated['reviewed_at']
    assert datetime.fromisoformat(result['evaluated_at']).utcoffset().total_seconds() == 0
    assert result['source_report_id'] == report['id'] and result['source_report_url'] == report['detail_url']
    assert 'Justificación privada' not in str(result)
    guest = TestClient(client.app)
    try:
        assert snapshot(guest) == result
        public = guest.get('/api/reports/' + report['id']).json()
        assert public['review_notes'] is None and public['attention_level'] == 'priority'
        assert 'Nivel de atención asignado: Atención prioritaria' in guest.get(report['detail_url']).text
        assert guest.get('/api/alerts').json()['items'] == []
    finally:
        guest.close()


def test_latest_evaluation_wins_regardless_of_citizen_condition_and_creation_order(client):
    older = send(client, payload(observed_condition='critico')).json()
    newer = send(client, payload(observed_condition='normal')).json()
    login(client)
    assign(client, newer, 'priority')
    first = snapshot(client)
    response = assign(client, older, 'monitoring')
    assert response.status_code == 200
    result = snapshot(client)
    assert result['level'] == 'monitoring' and result['source_report_id'] == older['id']
    assert result['evaluated_at'] >= first['evaluated_at']
    # Un reporte nuevo sin validar no modifica la evaluación.
    send(client, payload(observed_condition='critico'))
    assert snapshot(client) == result


def test_discard_and_return_to_pending_fall_back_to_last_currently_validated_report(client):
    first, second = send(client).json(), send(client).json()
    login(client)
    first = assign(client, first, 'preventive').json()
    second = assign(client, second, 'priority').json()
    assert snapshot(client)['source_report_id'] == second['id']
    discarded = review(client, second, 'discarded').json()
    assert discarded['attention_level'] is None and discarded['attention_label'] is None
    assert snapshot(client)['source_report_id'] == first['id']
    assert snapshot(client)['level'] == 'preventive'
    review(client, first, 'pending')
    assert snapshot(client)['level'] is None
    assert snapshot(client)['source_report_url'] is None


def test_evaluation_can_be_updated_and_stale_versions_cannot_replace_it(client):
    report = send(client).json()
    login(client)
    first = assign(client, report, 'priority').json()
    second = assign(client, first, 'preventive', 'Reevaluación privada').json()
    assert second['review_version'] == 2 and snapshot(client)['level'] == 'preventive'
    assert assign(client, first, 'monitoring').status_code == 409
    assert snapshot(client)['level'] == 'preventive'
    with client.app.state.database.connect() as db:
        rows = db.execute('SELECT attention_level,admin_id,notes FROM report_reviews ORDER BY sequence').fetchall()
        assert [row['attention_level'] for row in rows] == ['priority', 'preventive']
        assert all(row['admin_id'] for row in rows) and rows[-1]['notes'] == 'Reevaluación privada'


@pytest.mark.parametrize('changes', [
    {'attention_level': None}, {'attention_level': 'invented'}, {'notes': ''}, {'notes': '   '},
    {'decision': 'discarded'}, {'decision': 'pending'}, {'automatic_score': 99},
])
def test_invalid_or_unjustified_evaluations_are_rejected(client, changes):
    report = send(client).json()
    login(client)
    response = client.post('/api/reports/' + report['id'] + '/review', headers=csrf(client), json={
        'decision': 'validated', 'expected_version': 0, 'attention_level': 'priority',
        'notes': 'Justificación de prueba', **changes,
    })
    assert response.status_code == 422
    assert snapshot(client)['level'] is None
    assert client.get('/api/reports/' + report['id']).json()['review_version'] == 0
    with client.app.state.database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM report_reviews').fetchone()[0] == 0


def test_guest_and_normal_account_cannot_assign_attention(client):
    report = send(client).json()
    values = {'decision': 'validated', 'expected_version': 0, 'attention_level': 'priority', 'notes': 'Prueba'}
    assert client.post('/api/reports/' + report['id'] + '/review', json=values).status_code == 401
    register(client)
    assert client.post('/api/reports/' + report['id'] + '/review', headers=csrf(client), json=values).status_code == 403
    assert send(client, payload(attention_level='priority')).status_code == 422
    assert snapshot(client)['level'] is None


def test_legacy_validations_without_attention_require_a_new_evaluation_and_persist_after_restart(settings):
    with TestClient(create_app(settings)) as client:
        report = send(client).json()
        login(client)
        report = assign(client, report, 'priority').json()
        photo = client.get(report['photos'][0]['url']).content
        database = client.app.state.database
    # Reproduce una base con validaciones anteriores a esta función.
    with database.connect() as db:
        db.execute('ALTER TABLE reports DROP COLUMN attention_level')
        db.execute('ALTER TABLE report_reviews DROP COLUMN attention_level')
    with TestClient(create_app(settings)) as client:
        assert snapshot(client)['level'] is None
        existing = client.get('/api/reports/' + report['id']).json()
        assert existing['review_status'] == 'validated' and existing['attention_level'] is None
        assert existing['review_version'] == 1
        assert client.get(report['photos'][0]['url']).content == photo
        login(client)
        assert assign(client, existing, 'monitoring').status_code == 200
        state = snapshot(client)
    with TestClient(create_app(settings)) as client:
        assert snapshot(client) == state
        with database.connect() as db:
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            assert db.execute('SELECT COUNT(*) FROM report_reviews').fetchone()[0] == 2
