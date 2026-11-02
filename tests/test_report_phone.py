from uuid import uuid4

from fastapi.testclient import TestClient
import jwt
import pytest

from app.main import create_app
from app.schemas.auth import Credentials
from test_accounts_and_moderation import (
    ADMIN_PASSWORD, USER_PASSWORD, USER_PHONE, client, csrf, login, register, review, settings,
)
from test_reports import payload, send


@pytest.mark.parametrize('phone', [None, '', '123456789', '98765432', '9876543210', '9abcdefgh',
                                  '<script>alert(1)</script>', 987654321, True])
def test_registration_requires_a_valid_cell_number(client, phone):
    response = client.post('/api/auth/register', json={'username': 'new-phone-user', 'password': USER_PASSWORD,
        'password_confirmation': USER_PASSWORD, 'phone': phone})
    assert response.status_code == 422
    assert USER_PASSWORD not in response.text
    assert client.app.state.auth.repository.by_username('new-phone-user') is None


def test_registration_cannot_omit_phone_and_login_still_can(client):
    assert client.post('/api/auth/register', json={'username': 'without-phone', 'password': USER_PASSWORD,
        'password_confirmation': USER_PASSWORD}).status_code == 422
    assert login(client)['user']['phone'] is None


@pytest.mark.parametrize('phone', ['987654321', '+51 987 654 321', '51 987-654-321', '(987) 654-321'])
def test_account_phone_is_normalized_persisted_and_not_put_in_jwt(client, phone):
    session = register(client, phone=phone)
    assert session['user']['phone'] == USER_PHONE
    assert client.get('/api/auth/me').json()['user']['phone'] == USER_PHONE
    row = client.app.state.auth.repository.by_username('citizen')
    assert row['phone'] == USER_PHONE
    token = client.cookies['waki_access']
    claims = jwt.decode(token, options={'verify_signature': False})
    assert 'phone' not in claims
    assert USER_PHONE not in str(claims)


@pytest.mark.parametrize('phone', [None, '', '   '])
def test_omitted_contact_has_no_contact_display_for_admin(client, phone):
    report = send(client, payload(phone=phone)).json()
    assert report['review_status'] == 'pending'
    login(client)
    saved = client.get('/api/reports/' + report['id']).json()
    assert saved['phone'] is None
    assert 'Celular:' not in client.get(report['detail_url']).text


def test_phone_in_report_is_visible_only_to_admin_even_after_validation(client):
    number = '999123456'
    response = send(client, payload(phone='+51 999 123 456'))
    assert response.status_code == 201
    report = response.json()
    assert number not in response.text and report['phone'] is None
    assert report['review_status'] == 'pending' and report['attention_level'] is None
    login(client)
    saved = client.get('/api/reports/' + report['id']).json()
    assert saved['phone'] == number
    assert f'href="tel:+51{number}"' in client.get(report['detail_url']).text
    assert client.get('/api/reports?review_status=pending').json()['items'][0]['phone'] == number
    review(client, saved, 'validated')
    public = TestClient(client.app)
    for authenticated in (False, True):
        if authenticated:
            register(public, 'public-phone-user')
        for path in ['/api/reports', '/api/reports/' + report['id'], report['detail_url'], '/reportes']:
            response = public.get(path)
            assert response.status_code == 200
            assert number not in response.text
            assert f'tel:+51{number}' not in response.text
    public.close()


def test_account_contact_is_a_snapshot_and_explicit_blank_is_respected(client):
    register(client)
    automatic = send(client).json()
    explicit_blank = send(client, payload(phone=None)).json()
    edited = send(client, payload(phone='999123456')).json()
    assert client.get('/api/auth/me').json()['user']['phone'] == USER_PHONE
    assert client.put('/api/auth/phone', headers=csrf(client), json={'phone': '988123456'}).status_code == 200
    assert client.get('/api/auth/me').json()['user']['phone'] == '988123456'
    newer = send(client).json()
    login(client)
    for report, expected in [(automatic, USER_PHONE), (explicit_blank, None), (edited, '999123456'), (newer, '988123456')]:
        stored = client.get('/api/reports/' + report['id']).json()
        assert stored['phone'] == expected
        assert stored['review_status'] == 'pending' and stored['review_version'] == 0
        assert stored['attention_level'] is None


def test_changing_phone_requires_session_csrf_and_same_origin(client):
    assert client.put('/api/auth/phone', json={'phone': USER_PHONE}).status_code == 401
    register(client)
    assert client.put('/api/auth/phone', json={'phone': '999123456'}).status_code == 403
    assert client.put('/api/auth/phone', headers={**csrf(client), 'Origin': 'https://other.example'},
                      json={'phone': '999123456'}).status_code == 403
    assert client.put('/api/auth/phone', headers=csrf(client), json={'phone': '999123456', 'user_id': str(uuid4())}).status_code == 422
    assert client.put('/api/auth/phone', headers=csrf(client), json={'phone': ''}).status_code == 422
    assert client.get('/api/auth/me').json()['user']['phone'] == USER_PHONE
    response = client.put('/api/auth/phone', headers=csrf(client), json={'phone': '+51 999 123 456'})
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.json()['user']['phone'] == '999123456'
    assert client.get('/api/auth/me').json()['user']['phone'] == '999123456'


def test_legacy_users_and_report_contact_survive_migration_and_restart(settings):
    with TestClient(create_app(settings)) as first:
        # Antes del nuevo registro, una cuenta podía crearse sin celular.
        first.app.state.auth._create_user(Credentials(username='legacy-citizen', password=USER_PASSWORD), 'user')
        report = send(first, payload(phone=USER_PHONE)).json()
        database = first.app.state.database
        with database.connect() as db:
            db.execute('ALTER TABLE users DROP COLUMN phone')
    with TestClient(create_app(settings)) as second:
        session = login(second, 'legacy-citizen', USER_PASSWORD)
        assert session['user']['phone'] is None
        assert second.put('/api/auth/phone', headers=csrf(second), json={'phone': USER_PHONE}).status_code == 200
        login(second)
        assert second.get('/api/reports/' + report['id']).json()['phone'] == USER_PHONE
    with TestClient(create_app(settings)) as third:
        assert login(third, 'legacy-citizen', USER_PASSWORD)['user']['phone'] == USER_PHONE
        with database.connect() as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()


@pytest.mark.parametrize('phone', ['bad', '123456789', '98765432', '9876543210', '<script>9</script>'])
def test_invalid_report_phone_does_not_save_files_or_reports(client, phone):
    response = send(client, payload(phone=phone))
    assert response.status_code == 422 and phone not in response.text
    assert client.get('/api/reports').json()['total'] == 0
    assert not list(client.app.state.reports.images.directory.iterdir())


def test_phone_changes_are_part_of_idempotent_payload_without_changing_review(client):
    headers = {'Idempotency-Key': str(uuid4())}
    first = send(client, payload(phone=USER_PHONE), headers=headers)
    repeat = send(client, payload(phone=USER_PHONE), headers=headers)
    assert first.status_code == repeat.status_code == 201
    assert first.json()['id'] == repeat.json()['id']
    assert send(client, payload(phone='999123456'), headers=headers).status_code == 409
    assert first.json()['review_status'] == 'pending'


def test_contact_is_not_automatically_extracted_cross_origin(client):
    register(client)
    assert send(client, headers={'Origin': 'https://other.example'}).status_code == 403


def test_phone_inputs_are_short_optional_on_report_and_required_on_registration(client):
    html = client.get('/reportar').text
    assert 'id="report-phone"' in html and 'Celular (opcional)' in html
    assert html.index('id="descripcionCiudadana"') < html.index('id="report-phone"') < html.index('id="btnSubmitCitizen"')
    assert 'Solo visible para el administrador.' in html
    registration = client.get('/registro').text
    assert 'id="auth-phone"' in registration and 'name="phone"' in registration
    assert 'id="auth-phone"' not in client.get('/ingresar').text
    login(client)
    assert 'id="account-phone"' in client.get('/administrar').text
