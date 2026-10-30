import { element, localTime, requestJSON } from './utils.js';

const kindLabels = { inundacion: 'Inundación', derrumbe: 'Derrumbe', huaico: 'Huaico', otro: 'Evento peligroso' };
export const alertKind = value => kindLabels[value] || 'Aviso importante';

export function initAlerts() {
  const dialog = document.getElementById('important-notice-dialog');
  const list = document.getElementById('important-notice-list');
  const banner = document.getElementById('active-alert-banner');
  let active = new Map(), feed = null, stopped = false, cursor = 0;
  let acknowledged;
  try { acknowledged = new Set(JSON.parse(sessionStorage.getItem('waki-acknowledged-alerts') || '[]')); }
  catch { acknowledged = new Set(); }

  function render() {
    list.replaceChildren();
    const items = [...active.values()].sort((a, b) => b.created_at.localeCompare(a.created_at));
    for (const item of items) {
      const card = element('article', undefined, 'site-notice-card');
      card.dataset.noticeId = item.id;
      card.append(element('p', alertKind(item.kind), 'site-notice-kind'), element('h3', item.title),
        element('p', `Lugar: ${item.location}`), element('p', item.message),
        element('p', `${localTime(item.created_at)} (Lima) · Administración de WAKI`, 'site-muted'));
      list.append(card);
    }
    if (!items.length) list.append(element('p', 'No hay avisos importantes activos.'));
    document.querySelectorAll('[data-alert-count]').forEach(node => { node.textContent = items.length; node.hidden = !items.length; });
    banner.hidden = !items.length;
  }
  function open() {
    render();
    if (!dialog.open) dialog.showModal();
    document.getElementById('acknowledge-notices').focus({ preventScroll: true });
  }
  function notifyUnseen() {
    if ([...active.keys()].some(id => !acknowledged.has(id))) open();
  }
  document.addEventListener('click', event => { if (event.target.closest('[data-open-notices]')) open(); });
  dialog.addEventListener('cancel', event => event.preventDefault());
  document.getElementById('acknowledge-notices').addEventListener('click', () => {
    active.forEach((_, id) => acknowledged.add(id));
    try { sessionStorage.setItem('waki-acknowledged-alerts', JSON.stringify([...acknowledged].slice(-200))); } catch { /* El popup también funciona sin almacenamiento del navegador. */ }
    dialog.close();
  });
  function changed(item) {
    if (item.active) active.set(item.id, item); else active.delete(item.id);
    render();
    if (!active.size && dialog.open) dialog.close();
    notifyUnseen();
    document.dispatchEvent(new Event('alerts-changed'));
  }
  function connect(after) {
    if (stopped || !window.EventSource || feed) return;
    feed = new EventSource(`/api/events?after=${after}`);
    feed.addEventListener('open', () => document.dispatchEvent(new Event('reports-changed')));
    for (const type of ['alert_created', 'alert_closed']) feed.addEventListener(type, event => {
      try {
        cursor = Math.max(cursor, Number(event.lastEventId) || 0);
        changed(JSON.parse(event.data));
      } catch { /* La siguiente sincronización recupera el estado. */ }
    });
    feed.addEventListener('reports_changed', event => {
      cursor = Math.max(cursor, Number(event.lastEventId) || 0);
      document.dispatchEvent(new Event('reports-changed'));
    });
  }
  async function synchronize() {
    if (stopped) return;
    try {
      const snapshot = await requestJSON('/api/alerts');
      if (stopped || snapshot.cursor < cursor) return;
      cursor = snapshot.cursor;
      active = new Map(snapshot.items.map(item => [item.id, item]));
      render(); notifyUnseen();
      if (!active.size && dialog.open) dialog.close();
      connect(snapshot.cursor);
    } catch { /* EventSource se reconecta solo; también se reintenta la instantánea. */ }
  }
  let timer = setInterval(synchronize, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) synchronize(); });
  window.addEventListener('pagehide', () => { stopped = true; feed?.close(); feed = null; clearInterval(timer); });
  window.addEventListener('pageshow', event => {
    if (event.persisted) {
      stopped = false;
      timer = setInterval(synchronize, 15000);
      synchronize();
    }
  });
  synchronize();
}
