from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.services.auth import COOKIE_NAME
from test_accounts_and_moderation import (
    ADMIN_PASSWORD, USER_PASSWORD, client, csrf, login, register, settings,
)
from test_pages import PageParser
from test_reports import send

NEW_PASSWORD = 'new-password-for-test-456'


def password_values(current=ADMIN_PASSWORD):
    return {'current_password': current, 'new_password': NEW_PASSWORD,
            'password_confirmation': NEW_PASSWORD}


@pytest.mark.parametrize('path', ['/ingresar', '/registro', '/', '/reportar', '/reportes'])
def test_public_pages_have_global_notice_but_no_auth_admin_dialogs(client, path):
    response = client.get(path)
    assert response.status_code == 200
    ids = [attrs['id'] for _, attrs in PageParser(response.text).elements if 'id' in attrs]
    assert len(ids) == len(set(ids))
    assert 'important-notice-dialog' in ids
    assert 'js/site/index.js' in response.text
    assert 'auth-dialog' not in ids and 'admin-dialog' not in ids
    assert 'site-admin-toolbar' not in response.text
    if path in ('/ingresar', '/registro'):
        assert 'auth-form' in ids
        assert ('auth-password-confirmation' in ids) == (path == '/registro')


@pytest.mark.parametrize('path', ['/administrar', '/admin/avisos', '/admin/reportes'])
def test_pages_redirect_guest_then_enforce_roles(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303 and response.headers['cache-control'] == 'no-store'
    location = urlsplit(response.headers['location'])
    assert location.path == '/ingresar' and parse_qs(location.query)['next'] == [path]
    register(client)
    response = client.get(path)
    assert response.status_code == (200 if path == '/administrar' else 403)
    assert 'important-notice-dialog' in response.text
    assert 'admin-alert-form' not in response.text and 'admin-review-list' not in response.text


def test_admin_pages_and_menu_link_directly_to_tools(client):
    login(client)
    for path, form_id in [('/administrar', 'password-form'), ('/admin/avisos', 'admin-alert-form'),
                          ('/admin/reportes', 'admin-review-list')]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert f'id="{form_id}"' in response.text
        assert 'important-notice-dialog' in response.text
    root = client.get('/').text
    for destination in ('/administrar', '/admin/avisos', '/admin/reportes'):
        assert f'href="{destination}"' in root
    report = send(client).json()
    assert f'/admin/reportes?report_id={report["id"]}' in client.get(report['detail_url']).text
    assert f'data-report-id="{report["id"]}"' in client.get('/admin/reportes?report_id=' + report['id']).text
    assert client.get('/admin/reportes?report_id=invalid').status_code == 422


@pytest.mark.parametrize('destination', ['https://evil.example', '//evil.example', '/api/auth/me', '/ingresar'])
def test_login_return_destination_is_allowlisted(client, destination):
    page = client.get('/ingresar', params={'next': destination})
    assert 'data-destination="/"' in page.text
    login(client)
    response = client.get('/ingresar', params={'next': destination}, follow_redirects=False)
    assert response.headers['location'] == '/'


@pytest.mark.parametrize('normal', [False, True])
def test_password_change_requires_current_password_and_revokes_all_sessions(client, normal):
    old_password = USER_PASSWORD if normal else ADMIN_PASSWORD
    if normal: register(client)
    else: login(client)
    username = 'citizen' if normal else 'admin'
    old_token = client.cookies[COOKIE_NAME]
    with TestClient(client.app) as other:
        login(other, username, old_password)
        second_token = other.cookies[COOKIE_NAME]
        response = client.post('/api/auth/password', json=password_values(old_password), headers=csrf(client))
        assert response.status_code == 204
        assert response.headers['cache-control'] == 'no-store'
        assert COOKIE_NAME not in client.cookies
        assert other.get('/api/auth/me').json()['user'] is None
        for token in (old_token, second_token):
            assert client.app.state.auth.context(token) is None
    assert client.post('/api/auth/login', json={'username': username, 'password': old_password}).status_code == 401
    assert login(client, username, NEW_PASSWORD)['user']['role'] == ('user' if normal else 'admin')
    row = client.app.state.auth.repository.by_username(username)
    assert row['password_hash'].startswith('$argon2') and NEW_PASSWORD not in row['password_hash']


def test_password_change_rejects_guest_csrf_wrong_current_and_cross_origin(client):
    assert client.post('/api/auth/password', json=password_values()).status_code == 401
    login(client)
    assert client.post('/api/auth/password', json=password_values()).status_code == 403
    assert client.post('/api/auth/password', json=password_values(), headers={**csrf(client), 'Origin': 'https://evil.example'}).status_code == 403
    response = client.post('/api/auth/password', json=password_values('wrong-current-password'), headers=csrf(client))
    assert response.status_code == 400 and NEW_PASSWORD not in response.text
    assert client.get('/api/auth/me').json()['user']['role'] == 'admin'
    login(client)


@pytest.mark.parametrize('changes', [
    {'new_password': 'short'}, {'password_confirmation': 'different-password'},
    {'new_password': ADMIN_PASSWORD, 'password_confirmation': ADMIN_PASSWORD}, {'role': 'admin'},
])
def test_password_validation_never_echoes_secrets(client, changes):
    login(client)
    response = client.post('/api/auth/password', json={**password_values(), **changes}, headers=csrf(client))
    assert response.status_code == 422
    assert ADMIN_PASSWORD not in response.text and NEW_PASSWORD not in response.text
    assert login(client)['user']['role'] == 'admin'


def test_bootstrap_does_not_reset_changed_password_after_restart(settings):
    with TestClient(create_app(settings)) as first:
        login(first)
        assert first.post('/api/auth/password', json=password_values(), headers=csrf(first)).status_code == 204
    with TestClient(create_app(settings)) as second:
        assert second.post('/api/auth/login', json={'username': 'admin', 'password': ADMIN_PASSWORD}).status_code == 401
        assert login(second, password=NEW_PASSWORD)['user']['role'] == 'admin'
