import { element, localTime, requestJSON } from './utils.js';
import { hasAlertZone } from './alert-zones.js';
import { isNearbyAlert } from './nearby-notifications.js';

const kindLabels = { inundacion: 'Inundación', derrumbe: 'Derrumbe', erosion_fluvial: 'Erosión fluvial', huaico: 'Huaico', otro: 'Evento peligroso' };
export const alertKind = value => kindLabels[value] || 'Aviso importante';
let latestAlerts = [];
export const getActiveAlerts = () => latestAlerts;

export function alertMapLink(item) {
  const showZone = item.active && hasAlertZone(item) && item.id;
  const link = element('a', showZone ? 'Ver zona de peligro en el mapa' : 'Ver lugar en el mapa');
  const lat = item.latitude.toFixed(6), lon = item.longitude.toFixed(6);
  link.href = showZone ? `/?aviso=${encodeURIComponent(item.id)}`
    : `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=17/${lat}/${lon}`;
  link.target = '_blank'; link.rel = 'noopener noreferrer';
  return link;
}

export function initAlerts() {
  const dialog = document.getElementById('important-notice-dialog');
  const list = document.getElementById('important-notice-list');
  const banner = document.getElementById('active-alert-banner');
  let active = new Map(), feed = null, stopped = false, cursor = 0, nearbyOnly = false;
  let acknowledged;
  try { acknowledged = new Set(JSON.parse(sessionStorage.getItem('waki-acknowledged-alerts') || '[]')); }
  catch { acknowledged = new Set(); }

  function render() {
    list.replaceChildren();
    const allItems = [...active.values()].sort((a, b) => b.created_at.localeCompare(a.created_at));
    const items = nearbyOnly ? allItems.filter(isNearbyAlert) : allItems;
    document.getElementById('important-notice-title').textContent = nearbyOnly ? 'Aviso en tu zona' : 'Avisos de WAKI';
    for (const item of items) {
      const card = element('article', undefined, 'site-notice-card');
      card.dataset.noticeId = item.id;
      if (item.title !== alertKind(item.kind)) card.append(element('p', alertKind(item.kind), 'site-notice-kind'));
      card.append(element('h3', item.title),
        element('p', `Lugar: ${item.location}`), element('p', item.message),
        element('p', `${localTime(item.created_at)} (Lima) · Administración de WAKI`, 'site-muted'));
      if (hasAlertZone(item)) card.append(element('p', `Zona de peligro: radio de ${item.radius_m} m`));
      if (Number.isFinite(item.latitude) && Number.isFinite(item.longitude)) card.append(alertMapLink(item));
      list.append(card);
    }
    if (!items.length) list.append(element('p', 'No hay avisos importantes activos.'));
    document.querySelectorAll('[data-alert-count]').forEach(node => { node.textContent = allItems.length; node.hidden = !allItems.length; });
    banner.hidden = !allItems.length;
    latestAlerts = allItems;
    document.dispatchEvent(new CustomEvent('active-alerts-updated', { detail: allItems }));
    if (nearbyOnly && !items.length && dialog.open) dialog.close();
  }
  function open(nearby = false) {
    nearbyOnly = nearby;
    render();
    if (!dialog.open) dialog.showModal();
    document.getElementById('acknowledge-notices').focus({ preventScroll: true });
  }
  function notifyUnseen() {
    if (document.getElementById('nearby-notifications-dialog')?.open) return;
    if ([...active.values()].some(item => isNearbyAlert(item) && !acknowledged.has(item.id))) open(true);
  }
  document.addEventListener('click', event => { if (event.target.closest('[data-open-notices]')) open(); });
  dialog.addEventListener('cancel', event => event.preventDefault());
  document.getElementById('acknowledge-notices').addEventListener('click', () => {
    active.forEach((item, id) => { if (!nearbyOnly || isNearbyAlert(item)) acknowledged.add(id); });
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
  document.addEventListener('nearby-location-changed', () => { render(); notifyUnseen(); });
  document.getElementById('nearby-notifications-dialog')?.addEventListener('close', notifyUnseen);
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
