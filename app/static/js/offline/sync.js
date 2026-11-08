/* Reintentos y tiempos compartidos entre pestañas y sincronización de fondo. */
(() => {
  const channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('waki-report-outbox') : null;
  let running = null;
  async function notify() {
    channel?.postMessage({ type: 'outbox-changed' });
    if (typeof document !== 'undefined') document.dispatchEvent(new Event('outbox-changed'));
    else if (globalThis.clients) {
      const windows = await clients.matchAll({ type: 'window', includeUncontrolled: true });
      windows.forEach(client => client.postMessage({ type: 'outbox-changed' }));
    }
  }

  async function send(item) {
    const controller = new AbortController();
    const offline = () => controller.abort();
    const timer = setTimeout(() => controller.abort(), item.timeoutMs);
    globalThis.addEventListener('offline', offline);
    let changes;
    try {
      if (navigator.onLine === false) throw Error('offline');
      const data = new FormData();
      data.append('metadata', JSON.stringify(item.metadata));
      item.files.forEach(file => data.append('files', file.blob, file.name));
      const response = await fetch('/api/reports', {
        method: 'POST', headers: { 'Idempotency-Key': item.id }, body: data,
        credentials: 'omit', signal: controller.signal,
      });
      const result = await response.json().catch(() => null);
      if (response.ok && typeof result?.id === 'string' && typeof result?.detail_url === 'string') {
        changes = { state: 'sent', serverId: result.id, receivedAt: result.created_at,
          message: 'Reporte enviado. Pendiente de verificación por la administración.' };
      } else if (response.status >= 400 && response.status < 500 && ![408, 425, 429].includes(response.status)) {
        changes = { state: 'error', status: response.status, message: typeof result?.detail === 'string'
          ? result.detail : 'Revisa los datos y las fotografías: el servidor rechazó el reporte.' };
      } else {
        const seconds = Number(response.headers.get('Retry-After'));
        changes = { retryAfter: Number.isFinite(seconds) && seconds > 0 ? Math.min(seconds * 1000, 86400000) : 0 };
      }
    } catch { /* Un corte o timeout conserva exactamente el mismo contenido y clave. */ }
    finally {
      clearTimeout(timer);
      globalThis.removeEventListener('offline', offline);
    }
    if (!changes?.state) {
      const delay = Math.max(Math.min(30000 * 2 ** Math.min(item.attempts - 1, 6), 1800000), changes?.retryAfter || 0);
      changes = { state: 'pending', nextAttemptAt: Date.now() + delay,
        message: navigator.onLine === false ? 'Sin conexión. Guardado en este dispositivo.'
          : 'No se pudo confirmar la recepción. El reporte sigue guardado y se reintentará.' };
    }
    await WakiOutbox.finish(item.id, item.leaseToken, changes);
    await notify();
  }

  async function drain({ onlyId = null, force = false } = {}) {
    if (navigator.onLine === false) return;
    const items = (await WakiOutbox.list()).filter(item => !onlyId || item.id === onlyId).reverse();
    for (const row of items) {
      if (navigator.onLine === false) break;
      const item = await WakiOutbox.claim(row.id, force);
      if (!item) continue;
      await notify();
      await send(item);
    }
  }

  function run(options) {
    if (running) return running.then(() => run(options));
    running = drain(options).finally(() => { running = null; });
    return running;
  }
  globalThis.WakiReportSync = { run, notify };
})();
