from datetime import datetime, timezone
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import jwt
import pytest

from app.config import Settings
from app.main import create_app
from app.services.auth import COOKIE_NAME
from test_reports import send

ADMIN_PASSWORD = 'admin-test-password-123'
USER_PASSWORD = 'citizen-test-password-123'
USER_PHONE = '987654321'


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, senamhi_enabled=False, data_dir=tmp_path,
                    jwt_secret='test-secret-that-is-longer-than-thirty-two-characters',
                    admin_username='admin', admin_password=ADMIN_PASSWORD)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as instance:
        yield instance


def login(client, username='admin', password=ADMIN_PASSWORD):
    result = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert result.status_code == 200, result.text
    return result.json()


def register(client, username='citizen', phone=USER_PHONE):
    response = client.post('/api/auth/register', json={'username': username, 'password': USER_PASSWORD,
                                                       'password_confirmation': USER_PASSWORD, 'phone': phone})
    assert response.status_code == 201, response.text
    return response.json()


def csrf(client):
    return {'X-CSRF-Token': client.get('/api/auth/me').json()['csrf_token']}


def review(client, report, decision, notes=''):
    return client.post('/api/reports/' + report['id'] + '/review', headers=csrf(client), json={
        'decision': decision, 'notes': notes, 'expected_version': report['review_version'],
        **({'attention_level': 'monitoring', 'notes': notes or 'Evaluación de seguimiento de prueba'} if decision == 'validated' else {}),
    })


def alert_values():
    return {'kind': 'derrumbe', 'title': 'Aviso de prueba', 'location': 'Lugar ficticio de prueba',
            'message': 'Mensaje exclusivo del entorno de pruebas.'}


def test_public_dashboard_form_and_reporting_remain_available(client):
    assert client.get('/').status_code == 200
    assert client.get('/reportar').status_code == 200
    assert client.get('/reportes').status_code == 200
    assert client.get('/api/auth/me').json()['user'] is None
    result = send(client)
    assert result.status_code == 201 and result.json()['review_status'] == 'pending'
    assert COOKIE_NAME not in client.cookies


def test_registration_creates_only_normal_role_and_sets_jwt_cookie(client, settings):
    response = client.post('/api/auth/register', json={
        'username': 'Citizen', 'password': USER_PASSWORD, 'password_confirmation': USER_PASSWORD, 'phone': USER_PHONE,
    })
    assert response.status_code == 201
    session = response.json()
    assert session['user']['role'] == 'user' and session['csrf_token']
    token = client.cookies[COOKIE_NAME]
    claims = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=['HS256'], issuer='waki', audience='waki-web')
    assert claims['sub'] == session['user']['id'] and claims['exp'] > claims['iat']
    assert USER_PASSWORD not in response.text and 'password_hash' not in response.text
    cookie = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=lax' in cookie and 'max-age=' in cookie
    with client.app.state.database.connect() as db:
        stored = db.execute("SELECT * FROM users WHERE username_key='citizen'").fetchone()
        assert stored['role'] == 'user' and stored['password_hash'].startswith('$argon2')
        assert USER_PASSWORD not in stored['password_hash']


@pytest.mark.parametrize('changes', [
    {'username': 'ab'}, {'username': 'has space'}, {'password': 'short'},
    {'password_confirmation': 'does-not-match'}, {'role': 'admin'}, {'email': 'not-needed@example.com'},
])
def test_registration_validation_and_no_password_echo(client, changes):
    values = {'username': 'new-user', 'password': USER_PASSWORD, 'password_confirmation': USER_PASSWORD, 'phone': USER_PHONE, **changes}
    response = client.post('/api/auth/register', json=values)
    assert response.status_code == 422
    assert USER_PASSWORD not in response.text and 'does-not-match' not in response.text
    with client.app.state.database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1


def test_duplicate_usernames_are_case_insensitive(client):
    register(client, 'Citizen')
    response = client.post('/api/auth/register', json={'username': 'citizen', 'password': USER_PASSWORD, 'password_confirmation': USER_PASSWORD, 'phone': USER_PHONE})
    assert response.status_code == 409


def test_login_logout_and_revocation_of_copied_jwt(client):
    context = login(client)
    assert context['user']['role'] == 'admin'
    token = client.cookies[COOKIE_NAME]
    assert client.post('/api/auth/logout').status_code == 403
    assert client.post('/api/auth/logout', headers=csrf(client)).status_code == 204
    assert client.get('/api/auth/me').json()['user'] is None
    copied = TestClient(client.app)
    copied.cookies.set(COOKIE_NAME, token)
    assert copied.get('/api/auth/me').json()['user'] is None
    assert copied.post('/api/alerts', json=alert_values()).status_code == 401
    copied.close()


@pytest.mark.parametrize('username,password', [('admin', 'wrong-password'), ('unknown', ADMIN_PASSWORD)])
def test_invalid_login_has_generic_error(client, username, password):
    result = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert result.status_code == 401 and result.json()['detail'] == 'Usuario o contraseña incorrectos.'
    assert password not in result.text


@pytest.mark.parametrize('alteration', ['signature', 'expired', 'missing_exp', 'wrong_audience'])
def test_bad_jwt_cannot_grant_admin_access(client, settings, alteration):
    login(client)
    key = settings.jwt_secret.get_secret_value()
    claims = jwt.decode(client.cookies[COOKIE_NAME], key, algorithms=['HS256'], audience='waki-web')
    if alteration == 'expired': claims['exp'] = int(time.time()) - 1
    if alteration == 'missing_exp': del claims['exp']
    if alteration == 'wrong_audience': claims['aud'] = 'other-application'
    token = jwt.encode(claims, key if alteration != 'signature' else 'different-secret-with-sufficient-length', algorithm='HS256')
    client.cookies.clear(); client.cookies.set(COOKIE_NAME, token)
    assert client.get('/api/auth/me').json()['user'] is None
    assert client.post('/api/alerts', json=alert_values()).status_code == 401


def test_admin_role_is_read_from_database_not_token_claims(client, settings):
    register(client)
    key = settings.jwt_secret.get_secret_value()
    claims = jwt.decode(client.cookies[COOKIE_NAME], key, algorithms=['HS256'], audience='waki-web')
    claims['role'] = 'admin'
    client.cookies.clear(); client.cookies.set(COOKIE_NAME, jwt.encode(claims, key, algorithm='HS256'))
    assert client.get('/api/auth/me').json()['user']['role'] == 'user'
    assert client.post('/api/alerts', json=alert_values(), headers=csrf(client)).status_code == 403


def test_normal_users_and_guests_have_same_public_access_and_no_admin_functions(client):
    report = send(client).json()
    for authenticated in (False, True):
        if authenticated: register(client)
        assert client.get('/api/reports').json()['total'] == 0
        assert client.get(report['detail_url']).status_code == 404
        expected = 403 if authenticated else 401
        assert client.post('/api/alerts', json=alert_values()).status_code == expected
        assert client.post(f"/api/reports/{report['id']}/review", json={'decision': 'validated', 'expected_version': 0}).status_code == expected
        assert client.get('/api/reports?include_discarded=true').status_code == 403


def test_discarded_reports_are_archived_hidden_and_restorable(client):
    report = send(client).json()
    photo_url = report['photos'][0]['url']
    login(client)
    validated = review(client, report, 'validated', 'Comprobado en la prueba').json()
    assert validated['review_status'] == 'validated' and validated['review_version'] == 1
    discarded = review(client, validated, 'discarded', 'Nota privada del administrador').json()
    assert discarded['review_status'] == 'discarded' and discarded['review_version'] == 2
    assert client.get('/api/reports').json()['total'] == 0
    archive = client.get('/api/reports?review_status=discarded').json()
    assert archive['total'] == 1 and archive['items'][0]['id'] == report['id']
    assert archive['items'][0]['review_notes'] == 'Nota privada del administrador'
    assert client.get(report['detail_url']).status_code == 200
    assert client.get(photo_url).status_code == 200
    guest = TestClient(client.app)
    try:
        for signed_in in (False, True):
            if signed_in: register(guest, 'other-user')
            assert guest.get('/api/reports').json()['total'] == 0
            assert guest.get('/api/reports/' + report['id']).status_code == 404
            assert guest.get(report['detail_url']).status_code == 404
            assert guest.get(photo_url).status_code == 404
            assert guest.get('/api/reports?review_status=discarded').status_code == 403
        restored = review(client, discarded, 'pending').json()
        assert restored['review_status'] == 'pending'
        assert guest.get('/api/reports/' + report['id']).status_code == 404
        assert guest.get(photo_url).status_code == 404
        review(client, restored, 'validated')
        public = guest.get('/api/reports/' + report['id']).json()
        assert public['review_notes'] is None
        assert guest.get(photo_url).status_code == 200
    finally: guest.close()
    with client.app.state.database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM reports').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM report_photos').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM report_reviews').fetchone()[0] == 4


def test_review_rejects_stale_version_and_csrf_failures(client):
    report = send(client).json(); login(client)
    assert client.post('/api/reports/' + report['id'] + '/review', json={'decision': 'discarded', 'expected_version': 0}).status_code == 403
    first = review(client, report, 'validated')
    assert first.status_code == 200
    assert review(client, report, 'discarded').status_code == 409
    assert client.get('/api/reports/' + report['id']).json()['review_status'] == 'validated'
    with client.app.state.database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM report_reviews').fetchone()[0] == 1


def test_idempotency_cannot_reveal_discarded_report(client):
    headers = {'Idempotency-Key': str(uuid4())}
    report = send(client, headers=headers).json()
    login(client); review(client, report, 'discarded')
    client.post('/api/auth/logout', headers=csrf(client))
    response = send(client, headers=headers)
    assert response.status_code == 409 and set(response.json()) == {'detail'}
    assert 'photos' not in response.text


def test_cross_origin_auth_and_admin_writes_are_rejected(client):
    assert client.post('/api/auth/login', json={'username': 'admin', 'password': ADMIN_PASSWORD}, headers={'Origin': 'https://other.example'}).status_code == 403
    login(client)
    response = client.post('/api/alerts', json=alert_values(), headers={**csrf(client), 'Origin': 'https://other.example'})
    assert response.status_code == 403
    assert client.get('/api/alerts').json()['items'] == []


def test_alerts_are_public_persistent_and_generate_ordered_events(client):
    baseline = client.get('/api/alerts').json()
    assert baseline['items'] == []
    login(client)
    assert client.post('/api/alerts', json=alert_values()).status_code == 403
    result = client.post('/api/alerts', json=alert_values(), headers=csrf(client))
    assert result.status_code == 201, result.text
    alert = result.json()
    assert alert['active'] and datetime.fromisoformat(alert['created_at']).utcoffset().total_seconds() == 0
    guest = TestClient(client.app)
    snapshot = guest.get('/api/alerts').json()
    assert snapshot['items'][0]['id'] == alert['id'] and snapshot['cursor'] > baseline['cursor']
    assert 'created_by' not in result.text and 'closed_by' not in result.text
    updates = client.app.state.alerts.events(baseline['cursor'])
    assert updates[0]['type'] == 'alert_created' and updates[0]['data']['id'] == alert['id']
    assert guest.post('/api/alerts/' + alert['id'] + '/close').status_code == 401
    assert client.post('/api/alerts/' + alert['id'] + '/close', headers=csrf(client)).status_code == 200
    assert guest.get('/api/alerts').json()['items'] == []
    events = client.app.state.alerts.events(snapshot['cursor'])
    assert events[0]['type'] == 'alert_closed' and events[0]['data']['active'] is False
    assert events[0]['id'] > snapshot['cursor']
    guest.close()


def test_report_events_do_not_expose_private_or_discarded_data(client):
    report = send(client).json(); login(client)
    review(client, report, 'discarded', 'Private review note')
    events = client.app.state.alerts.events(0)
    assert len(events) == 2
    assert all(event['type'] == 'reports_changed' and event['data'] == {} for event in events)


@pytest.mark.parametrize('changes', [{'kind': 'invented'}, {'title': 'x'}, {'message': ''}, {'location': ''}, {'active': False}])
def test_alert_validation_does_not_publish_invalid_messages(client, changes):
    login(client)
    response = client.post('/api/alerts', json={**alert_values(), **changes}, headers=csrf(client))
    assert response.status_code == 422 and client.get('/api/alerts').json()['items'] == []


def test_login_rate_limit_is_enforced(client):
    for _ in range(30):
        client.app.state.auth.throttle('testclient', 'login')
    assert client.post('/api/auth/login', json={'username': 'admin', 'password': ADMIN_PASSWORD}).status_code == 429


def test_jwt_secret_and_sessions_survive_restart(tmp_path):
    settings = Settings(_env_file=None, senamhi_enabled=False, data_dir=tmp_path, admin_username='admin', admin_password=ADMIN_PASSWORD)
    with TestClient(create_app(settings)) as first:
        login(first); token = first.cookies[COOKIE_NAME]
        key = first.app.state.auth.secret
    with TestClient(create_app(settings)) as second:
        assert second.app.state.auth.secret == key
        second.cookies.set(COOKIE_NAME, token)
        assert second.get('/api/auth/me').json()['user']['role'] == 'admin'


def test_existing_reports_gain_review_state_without_losing_photos(settings):
    with TestClient(create_app(settings)) as original:
        report = send(original).json()
        login(original)
        photo = original.get(report['photos'][0]['url']).content
        database = original.app.state.database
    # Reproduce el esquema anterior, que no tenía columnas de moderación.
    with database.connect() as db:
        db.execute('DROP INDEX reports_review')
        for column in ('review_status', 'reviewed_at', 'reviewed_by', 'review_notes', 'review_version'):
            db.execute(f'ALTER TABLE reports DROP COLUMN {column}')
    with TestClient(create_app(settings)) as updated:
        assert updated.get('/api/reports/' + report['id']).status_code == 404
        login(updated)
        migrated = updated.get('/api/reports/' + report['id']).json()
        assert migrated['review_status'] == 'pending' and migrated['review_version'] == 0
        assert migrated['observations'] == report['observations']
        assert updated.get(report['photos'][0]['url']).content == photo
        assert updated.get('/api/reports').json()['total'] == 1
        assert review(updated, migrated, 'validated').status_code == 200


def test_bootstrap_never_promotes_existing_normal_account(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False)
    with TestClient(create_app(settings)) as first: register(first, 'future-admin')
    configured = settings.model_copy(update={'admin_username': 'future-admin', 'admin_password': __import__('pydantic').SecretStr(ADMIN_PASSWORD)})
    with TestClient(create_app(configured)) as second:
        session = login(second, 'future-admin', USER_PASSWORD)
        assert session['user']['role'] == 'user'


def test_invalid_event_cursor_is_rejected_before_opening_stream(client):
    assert client.get('/api/events?after=-1').status_code == 422
    assert client.get('/api/events?after=99999999999999999999').status_code == 422
