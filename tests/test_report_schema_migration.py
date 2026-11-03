from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from test_accounts_and_moderation import ADMIN_PASSWORD, login, review
from test_reports import payload, send


@pytest.mark.parametrize('reviewed', [False, True])
def test_old_zone_and_contact_columns_are_removed_without_losing_reports(tmp_path, reviewed):
    settings = Settings(_env_file=None, data_dir=tmp_path, senamhi_enabled=False,
                        admin_username='admin', admin_password=ADMIN_PASSWORD)
    with TestClient(create_app(settings)) as client:
        report = send(client, payload(observations='Observación anterior a la migración')).json()
        login(client)
        photo = client.get(report['photos'][0]['url']).content
        if reviewed:
            report = review(client, report, 'validated', 'Revisión que debe conservarse').json()
        database = client.app.state.database

    legacy = {
        'river_section': ('TEXT', 'Río Chillón'),
        'district': ('TEXT', 'Distrito anterior'),
        'reference': ('TEXT', 'Referencia anterior'),
        'anonymous': ('INTEGER', 0),
        'contact_name': ('TEXT', 'Nombre de prueba anterior'),
        'contact_phone': ('TEXT', '999111222'),
        'neighborhood': ('TEXT', 'Barrio de prueba anterior'),
    }
    with database.connect() as db:
        db.execute('ALTER TABLE reports DROP COLUMN other_situation')
        if not reviewed:
            db.execute('DROP INDEX reports_review')
            for column in ('review_status', 'reviewed_at', 'reviewed_by', 'review_notes', 'review_version'):
                db.execute(f'ALTER TABLE reports DROP COLUMN {column}')
        for column, (kind, value) in legacy.items():
            db.execute(f'ALTER TABLE reports ADD COLUMN {column} {kind}')
            db.execute(f'UPDATE reports SET {column}=?', (value,))

    with TestClient(create_app(settings)) as client:
        login(client)
        migrated = client.get('/api/reports/' + report['id']).json()
        for key in ('id', 'created_at', 'observations', 'other_situation', 'latitude', 'longitude', 'photos', 'review_status', 'review_version'):
            assert migrated[key] == report[key], key
        assert not set(legacy).intersection(migrated)
        assert client.get(report['photos'][0]['url']).content == photo
        if reviewed:
            assert client.get('/api/reports/' + report['id']).json()['review_notes'] == 'Revisión que debe conservarse'
        with database.connect() as db:
            columns = {row['name'] for row in db.execute('PRAGMA table_info(reports)')}
            assert not set(legacy).intersection(columns)
            assert db.execute('SELECT COUNT(*) FROM report_photos').fetchone()[0] == 1
            assert db.execute('SELECT COUNT(*) FROM report_reviews').fetchone()[0] == int(reviewed)
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert send(client, {'observed_condition': 'normal'}).status_code == 201

    with TestClient(create_app(settings)) as client:
        assert client.get('/api/reports').json()['total'] == int(reviewed)
        login(client)
        assert client.get('/api/reports').json()['total'] == 2
        assert client.get(report['photos'][0]['url']).content == photo
