"""Pruebas reales: WAKI_BROWSER_TESTS=1 python -m pytest tests/browser -q.

Instalar requirements-browser.txt y ejecutar python -m playwright install chromium.
WAKI_BROWSER_EXECUTABLE permite reutilizar un Chromium instalado.
"""
import io
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request

from PIL import Image
import pytest

pytestmark = pytest.mark.skipif(os.getenv('WAKI_BROWSER_TESTS') != '1', reason='Pruebas de navegador opcionales')


@pytest.fixture(scope='module')
def server(tmp_path_factory):
    directory = tmp_path_factory.mktemp('waki-browser')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    env = {**os.environ, 'DATA_DIR': str(directory), 'SENAMHI_ENABLED': 'false',
           'MODEL_PROVIDER': 'none', 'PUSH_ENABLED': 'false', 'ADMIN_USERNAME': '',
           'ADMIN_PASSWORD': '', 'REPORT_UPLOAD_TIMEOUT_SECONDS': '10'}
    with (directory / 'server.log').open('w') as output:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                                    '--port', str(port)], cwd=Path(__file__).resolve().parents[2], env=env,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    pytest.fail((directory / 'server.log').read_text())
                try:
                    urllib.request.urlopen(url + '/api/health', timeout=.5).close()
                    break
                except OSError:
                    time.sleep(.1)
            else:
                pytest.fail('No arrancó el servidor de pruebas')
            yield url, directory
        finally:
            process.terminate()
            process.wait(timeout=15)


@pytest.fixture
def browser():
    api = pytest.importorskip('playwright.sync_api')
    with api.sync_playwright() as playwright:
        options = {'headless': True}
        if os.getenv('WAKI_BROWSER_EXECUTABLE'):
            options['executable_path'] = os.environ['WAKI_BROWSER_EXECUTABLE']
        instance = playwright.chromium.launch(**options)
        yield instance
        instance.close()


@pytest.fixture
def context(browser):
    context = browser.new_context()
    # Las pruebas de reintentos de primer plano controlan el momento del envío.
    context.add_init_script("Object.defineProperty(ServiceWorkerRegistration.prototype, 'sync', { get: () => undefined });")
    yield context
    context.close()


def open_form(context, server):
    page = context.new_page()
    page.goto(server[0] + '/reportar')
    page.wait_for_function("document.getElementById('reportOfflineReady').textContent.includes('preparado para abrirse')")
    page.wait_for_function('navigator.serviceWorker.controller !== null')
    return page


def fill(page, text='Observación sin conexión'):
    photo = io.BytesIO()
    Image.new('RGB', (80, 40), 'blue').save(photo, 'JPEG')
    page.locator('.citizen-risk-card[data-risk="normal"]').click()
    page.locator('#descripcionCiudadana').fill(text)
    page.locator('#citizenPhotoInput').set_input_files({'name': 'rio.jpg', 'mimeType': 'image/jpeg', 'buffer': photo.getvalue()})
    page.wait_for_function("document.getElementById('photoValidationStatus').textContent === ''")
    assert page.locator('.photo-preview').count() == 1


def rows(page):
    return page.evaluate('WakiOutbox.list()')


def wait_rows(page, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = rows(page)
        if predicate(result):
            return result
        page.wait_for_timeout(100)
    pytest.fail(f'No se alcanzó el estado esperado: {rows(page)}')


def report_count(server):
    with sqlite3.connect(server[1] / 'waki.sqlite3') as db:
        return db.execute('SELECT COUNT(*) FROM reports').fetchone()[0]


@pytest.mark.parametrize('mobile', [False, True])
def test_offline_immediate_persistent_and_reconnect(context, server, mobile):
    page = open_form(context, server)
    if mobile:
        page.set_viewport_size({'width': 390, 'height': 844})
    context.set_offline(True)
    page.reload()  # Abre realmente el formulario y sus módulos desde caché.
    fill(page)
    requests = []
    page.on('request', lambda request: requests.append(request.url) if request.method == 'POST' else None)
    started = time.monotonic()
    page.locator('#btnSubmitCitizen').click()
    page.wait_for_function("document.getElementById('reportSubmitStatus').textContent.includes('Pendiente de envío')")
    assert time.monotonic() - started < 3
    assert requests == []
    local = rows(page)[0]
    assert local['state'] == 'pending' and local['attempts'] == 0
    item = page.evaluate('(id) => WakiOutbox.get(id)', local['id'])
    assert item['files'][0]['name'] == 'rio.jpg'
    page.close()
    page = context.new_page()
    page.goto(server[0] + '/reportar')
    page.wait_for_function('globalThis.WakiOutbox !== undefined')
    assert rows(page)[0]['id'] == local['id']
    before = report_count(server)
    context.set_offline(False)
    sent = wait_rows(page, lambda rows: rows and rows[0]['state'] == 'sent')[0]
    assert sent['serverId'] and 'metadata' not in sent
    assert page.evaluate('(id) => WakiOutbox.get(id).then(row => row.files.length)', local['id']) == 0
    assert report_count(server) == before + 1
    with sqlite3.connect(server[1] / 'waki.sqlite3') as db:
        stored_date = db.execute('SELECT client_created_at FROM reports WHERE id=?', (sent['serverId'],)).fetchone()[0]
        assert datetime.fromisoformat(stored_date) == datetime.fromisoformat(local['createdAt'])
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def test_slow_connection_then_success(context, server):
    page = open_form(context, server)
    def delayed(route):
        time.sleep(1)
        route.continue_()
    page.route('**/api/reports', delayed)
    fill(page, 'Envío lento')
    page.locator('#btnSubmitCitizen').click()
    wait_rows(page, lambda rows: any(row['state'] == 'sending' for row in rows))
    assert 'Enviando reporte' in page.locator('#reportSubmitStatus').inner_text()
    wait_rows(page, lambda rows: rows and rows[0]['state'] == 'sent')


def test_timeout_keeps_photos_and_retry_uses_same_key(context, server):
    page = open_form(context, server)
    page.route('**/api/reports', lambda route: None)  # Red que nunca responde.
    fill(page, 'Sin respuesta')
    page.locator('#btnSubmitCitizen').click()
    wait_rows(page, lambda rows: rows and rows[0]['state'] == 'sending')
    key = rows(page)[0]['id']
    wait_rows(page, lambda rows: rows and rows[0]['state'] == 'pending' and rows[0]['attempts'] == 1, timeout=15)
    assert page.evaluate('(id) => WakiOutbox.get(id).then(row => row.files.length)', key) == 1
    page.unroute('**/api/reports')
    page.locator('#retryPendingReports').click()
    wait_rows(page, lambda rows: rows and rows[0]['state'] == 'sent')
    assert rows(page)[0]['id'] == key and rows(page)[0]['attempts'] == 2


def test_lost_response_does_not_duplicate_report(context, server):
    page = open_form(context, server)
    before = report_count(server)
    def lose_response(route):
        route.fetch()  # El servidor recibió el reporte, pero el navegador pierde su respuesta.
        route.abort('failed')
    page.route('**/api/reports', lose_response)
    fill(page, 'Respuesta perdida')
    page.locator('#btnSubmitCitizen').click()
    wait_rows(page, lambda rows: rows and rows[0]['state'] == 'pending' and rows[0]['attempts'] == 1)
    key = rows(page)[0]['id']
    assert report_count(server) == before + 1
    page.unroute('**/api/reports')
    page.locator('#retryPendingReports').click()
    wait_rows(page, lambda rows: rows and rows[0]['state'] == 'sent')
    assert rows(page)[0]['id'] == key
    assert report_count(server) == before + 1


def test_storage_failure_preserves_form_and_sends_nothing(context, server):
    page = open_form(context, server)
    before = report_count(server)
    page.evaluate("""() => {
      const add = IDBObjectStore.prototype.add;
      IDBObjectStore.prototype.add = function (...args) {
        if (this.name === 'photos') throw new DOMException('full', 'QuotaExceededError');
        return add.apply(this, args);
      };
    }""")
    fill(page, 'Sin espacio')
    page.locator('#btnSubmitCitizen').click()
    page.wait_for_function("!document.getElementById('reportSubmitError').hidden")
    assert 'No hay espacio' in page.locator('#reportSubmitError').inner_text()
    assert page.locator('#descripcionCiudadana').input_value() == 'Sin espacio'
    assert page.locator('.photo-preview').count() == 1
    assert rows(page) == [] and report_count(server) == before


def test_rejected_report_can_be_corrected_without_losing_photos(context, server):
    page = open_form(context, server)
    page.route('**/api/reports', lambda route: route.fulfill(status=422, json={'detail': 'Corrige la observación'}))
    fill(page, 'Necesita corrección')
    page.locator('#report-phone').fill('999111222')
    page.locator('#btnSubmitCitizen').click()
    wait_rows(page, lambda rows: rows and rows[0]['state'] == 'error')
    page.get_by_role('button', name='Cargar para corregir').click()
    page.wait_for_function("!document.getElementById('reportEditingNotice').hidden")
    assert page.locator('.photo-preview').count() == 1
    assert page.locator('#report-phone').input_value() == '999111222'
    old_key = rows(page)[0]['id']
    page.locator('#descripcionCiudadana').fill('Observación corregida')
    page.unroute('**/api/reports')
    page.locator('#btnSubmitCitizen').click()
    wait_rows(page, lambda rows: len(rows) == 1 and rows[0]['state'] == 'sent')
    assert rows(page)[0]['id'] != old_key


def test_two_tabs_claim_only_one_upload_and_cache_excludes_private_pages(context, server):
    page = open_form(context, server)
    context.set_offline(True)
    fill(page, 'Dos pestañas')
    page.locator('#btnSubmitCitizen').click()
    wait_rows(page, lambda rows: len(rows) == 1)
    other = context.new_page()
    other.goto(server[0] + '/reportar')
    other.wait_for_function('globalThis.WakiOutbox !== undefined')
    before = report_count(server)
    context.set_offline(False)
    page.evaluate('WakiReportSync.run({force: true})')
    other.evaluate('WakiReportSync.run({force: true})')
    wait_rows(page, lambda rows: rows and rows[0]['state'] == 'sent')
    assert rows(page)[0]['attempts'] == 1
    assert report_count(server) == before + 1
    cached = page.evaluate("""async () => {
      const urls = [];
      for (const name of await caches.keys()) {
        for (const request of await (await caches.open(name)).keys()) urls.push(new URL(request.url).pathname);
      }
      return urls;
    }""")
    assert '/reportar' in cached
    assert all(url == '/reportar' or url.startswith('/static/') for url in cached)


def test_connection_lost_during_upload_stops_waiting_and_keeps_report(context, server):
    page = open_form(context, server)
    page.route('**/api/reports', lambda route: None)
    fill(page, 'Corte durante el envío')
    page.locator('#btnSubmitCitizen').click()
    wait_rows(page, lambda rows: rows and rows[0]['state'] == 'sending')
    started = time.monotonic()
    context.set_offline(True)
    wait_rows(page, lambda rows: rows and rows[0]['state'] == 'pending', timeout=3)
    assert time.monotonic() - started < 3
    assert page.evaluate('(id) => WakiOutbox.get(id).then(row => row.files.length)', rows(page)[0]['id']) == 1


def test_expired_upload_reservation_recovers_without_changing_key(context, server):
    page = open_form(context, server)
    context.set_offline(True)
    fill(page, 'Envío interrumpido al cerrar')
    page.locator('#btnSubmitCitizen').click()
    item = wait_rows(page, lambda rows: len(rows) == 1)[0]
    page.evaluate("""async id => {
      await WakiOutbox.claim(id);
      const db = await new Promise(resolve => { const req = indexedDB.open('waki-report-outbox'); req.onsuccess = () => resolve(req.result); });
      await new Promise(resolve => {
        const tx = db.transaction('reports', 'readwrite');
        const store = tx.objectStore('reports');
        store.get(id).onsuccess = event => { const row = event.target.result; row.leaseUntil = 0; store.put(row); };
        tx.oncomplete = resolve;
      });
      db.close();
    }""", item['id'])
    context.set_offline(False)
    sent = wait_rows(page, lambda rows: rows and rows[0]['state'] == 'sent')[0]
    assert sent['id'] == item['id'] and sent['attempts'] == 2


def test_worker_can_send_with_no_form_open(context, server):
    page = open_form(context, server)
    context.set_offline(True)
    fill(page, 'Envío desde el worker')
    page.locator('#btnSubmitCitizen').click()
    item = wait_rows(page, lambda rows: len(rows) == 1)[0]
    worker = context.service_workers[0]
    page.close()
    before = report_count(server)
    context.set_offline(False)
    worker.evaluate('WakiReportSync.run({force: true})')
    assert report_count(server) == before + 1
    with sqlite3.connect(server[1] / 'waki.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM reports WHERE request_key=?', (item['id'],)).fetchone()[0] == 1


def test_pending_survives_closing_and_relaunching_browser(browser, server, tmp_path):
    options = {'headless': True}
    if os.getenv('WAKI_BROWSER_EXECUTABLE'):
        options['executable_path'] = os.environ['WAKI_BROWSER_EXECUTABLE']
    profile = tmp_path / 'browser-profile'
    context = browser.browser_type.launch_persistent_context(profile, **options)
    try:
        context.add_init_script("Object.defineProperty(ServiceWorkerRegistration.prototype, 'sync', { get: () => undefined });")
        page = open_form(context, server)
        context.set_offline(True)
        fill(page, 'Conservar después de cerrar el navegador')
        page.locator('#btnSubmitCitizen').click()
        item = wait_rows(page, lambda rows: len(rows) == 1)[0]
    finally:
        context.close()
    context = browser.browser_type.launch_persistent_context(profile, **options)
    try:
        context.set_offline(True)
        page = context.new_page()
        page.goto(server[0] + '/reportar')
        page.wait_for_function('globalThis.WakiOutbox !== undefined')
        restored = rows(page)[0]
        assert restored['id'] == item['id'] and restored['state'] == 'pending'
        assert page.evaluate('(id) => WakiOutbox.get(id).then(row => row.files.length)', item['id']) == 1
    finally:
        context.close()
