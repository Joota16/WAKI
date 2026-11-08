import '../offline/client.js';

export function initOutboxView({ onEdit }) {
  const list = document.getElementById('reportOutboxList');
  const status = document.getElementById('reportOutboxStatus');
  const connection = document.getElementById('reportConnectionStatus');
  const retry = document.getElementById('retryPendingReports');
  const ready = document.getElementById('reportOfflineReady');
  const format = date => new Date(date).toLocaleString('es-PE', { timeZone: 'America/Lima' });
  let revision = 0;

  function online() {
    connection.textContent = navigator.onLine === false
      ? 'Sin conexión. Al enviar, el reporte se guardará en este dispositivo.'
      : 'Tus reportes se guardan primero en este dispositivo antes de enviarse.';
  }
  async function offlineReady() {
    if (!('caches' in window)) return;
    try {
      const names = (await caches.keys()).filter(name => name.startsWith('waki-report-form-'));
      const available = navigator.serviceWorker?.controller && names.length
        && await (await caches.open(names[names.length - 1])).match('/reportar');
      ready.textContent = available ? 'Formulario preparado para abrirse sin conexión en este navegador.'
        : 'Abre WAKI con conexión y espera a que el formulario quede preparado para usarlo sin internet.';
    } catch { ready.textContent = 'No se pudo preparar la apertura del formulario sin conexión.'; }
  }
  function button(text, action) {
    const node = document.createElement('button');
    node.type = 'button'; node.textContent = text;
    node.addEventListener('click', async () => {
      node.disabled = true;
      try { await action(); }
      catch (error) { status.textContent = error.message; }
      finally { node.disabled = false; }
    });
    return node;
  }
  async function render() {
    const current = ++revision;
    try {
      const rows = await WakiOutbox.list();
      if (current !== revision) return;
      list.replaceChildren();
      const pending = rows.filter(row => row.state !== 'sent').length;
      status.textContent = rows.length ? `${pending} ${pending === 1 ? 'reporte pendiente' : 'reportes pendientes'} en este dispositivo.`
        : 'No tienes reportes pendientes en este dispositivo.';
      retry.disabled = navigator.onLine === false || !rows.some(row => row.state === 'pending'
        || (row.state === 'sending' && row.leaseUntil <= Date.now()));
      for (const row of rows) {
        const item = document.createElement('li'); item.dataset.localReport = row.id;
        const title = document.createElement('strong');
        const sending = navigator.onLine !== false && row.state === 'sending' && row.leaseUntil > Date.now();
        title.textContent = row.state === 'sent' ? 'Reporte enviado' : row.state === 'error'
          ? 'Requiere revisión' : sending ? 'Enviando reporte…' : 'Pendiente de envío';
        const date = document.createElement('p');
        date.textContent = `Creado: ${format(row.createdAt)} (Lima) · ${row.photoCount} foto(s)`;
        const description = document.createElement('p');
        description.textContent = row.metadata?.observations || (row.state === 'sent' ? `Identificador: ${row.serverId}` : 'Reporte ciudadano');
        const message = document.createElement('p');
        message.textContent = row.message || (sending ? 'Tus datos siguen guardados mientras se confirma el envío.'
          : 'Guardado en este dispositivo. Se intentará enviar cuando haya conexión con WAKI.');
        item.append(title, date, description, message);
        if (row.state === 'sent') {
          const received = document.createElement('p'); received.textContent = `Recibido por WAKI: ${format(row.receivedAt)} (Lima)`;
          item.append(received);
        }
        const actions = document.createElement('div'); actions.className = 'report-outbox-actions';
        if (row.state === 'error' && [400, 413, 415, 422].includes(row.status)) actions.append(button('Cargar para corregir', () => onEdit(row.id)));
        if (!sending) actions.append(button(row.state === 'sent' ? 'Quitar comprobante' : 'Eliminar pendiente', async () => {
          if (!window.confirm(row.state === 'sent' ? '¿Quitar este comprobante del dispositivo? El reporte seguirá en WAKI.'
            : '¿Eliminar este pendiente y sus fotos del dispositivo? Si hubo un envío sin confirmación, puede haber sido recibido por WAKI.')) return;
          await WakiOutbox.remove(row.id); await WakiReportSync.notify();
        }));
        item.append(actions); list.append(item);
      }
    } catch {
      status.textContent = 'No se puede acceder al almacenamiento local. Comprueba los permisos y el espacio disponible del navegador.';
      retry.disabled = true;
    }
  }
  retry.addEventListener('click', async () => {
    retry.disabled = true;
    try { await WakiReportSync.run({ force: true }); }
    catch { status.textContent = 'No se pudo reintentar. Los reportes siguen guardados en el dispositivo.'; }
    finally { render(); }
  });
  document.addEventListener('outbox-changed', render);
  document.addEventListener('offline-ready-changed', offlineReady);
  navigator.serviceWorker?.addEventListener('controllerchange', offlineReady);
  for (const event of ['online', 'offline']) window.addEventListener(event, () => { online(); render(); });
  let timer = setInterval(render, 15000);
  window.addEventListener('pagehide', () => clearInterval(timer));
  window.addEventListener('pageshow', event => { if (event.persisted) { timer = setInterval(render, 15000); render(); offlineReady(); } });
  online(); render(); offlineReady();
}
