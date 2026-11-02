import { authenticatedJSON, getSession } from './auth.js';
import { alertMapLink } from './alerts.js';
import { createAlertCircle } from './alert-zones.js';
import { element, localTime, message } from './utils.js';

export function initAdminAlerts() {
  const $ = id => document.getElementById(id);
  const form = $('admin-alert-form'), status = $('admin-status'), kind = $('admin-alert-kind');
  const place = $('admin-alert-source'), instruction = $('admin-alert-message-option'), publish = $('admin-publish-alert');
  const radius = $('admin-alert-radius');
  const mapStatus = $('admin-alert-map-status'), historyFilter = $('admin-alert-history-filter');
  let catalog = null, sources = new Map(), sourceOffset = 0, historyOffset = 0;
  let optionsSequence = 0, historySequence = 0, activeSequence = 0, publishing = false;
  let map = null, markers = null, zone = null, loadingOptions = false;
  const isAdmin = () => getSession().user?.role === 'admin';
  const key = item => `${item.source_type}:${item.source_id}`;
  const selected = () => sources.get(place.value);
  const radiusValue = () => Number.isInteger(radius.valueAsNumber) && radius.valueAsNumber >= 1 && radius.valueAsNumber <= 10000
    ? radius.valueAsNumber : null;

  function preview() {
    const event = catalog?.kinds.find(item => item.id === kind.value), source = selected();
    const template = catalog?.messages.find(item => item.id === instruction.value);
    $('admin-alert-preview-title').textContent = event?.label || 'Aviso importante';
    $('admin-alert-preview-location').textContent = source?.configured ? source.location : 'Selecciona un lugar con ubicación.';
    $('admin-alert-preview-message').textContent = source?.configured && template && event ? template.text : '';
    const zoneDescription = $('admin-alert-preview-radius');
    zoneDescription.hidden = !source?.configured || radiusValue() === null;
    zoneDescription.textContent = zoneDescription.hidden ? '' : `Zona de peligro: radio de ${radiusValue()} m`;
    publish.disabled = !isAdmin() || loadingOptions || publishing || !source?.configured || !template || radiusValue() === null;
  }
  function drawZone(fit = false) {
    zone?.remove(); zone = null;
    const source = selected(), meters = radiusValue();
    if (!map || !source?.configured || meters === null) return;
    zone = createAlertCircle(window.L, { ...source, radius_m: meters }).addTo(map);
    if (fit) map.fitBounds(zone.getBounds(), { padding: [30, 30], maxZoom: 18, animate: false });
  }

  function createMap() {
    if (map || !window.L) return;
    map = window.L.map('admin-alert-map', { zoomAnimation: false }).setView([-11.85, -77.02], 10);
    window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    markers = window.L.layerGroup().addTo(map);

  }
  function showLocation() {
    createMap();
    const source = selected();
    if (!map) {
      mapStatus.hidden = false;
      mapStatus.replaceChildren(element('span', 'No se pudo cargar el mapa. Puedes consultar el lugar en el enlace.'));
      if (source?.configured) mapStatus.append(' ', alertMapLink(source));
      return;
    }
    markers.clearLayers();
    mapStatus.hidden = true; mapStatus.textContent = '';
    const bounds = [];
    for (const item of sources.values()) {
      if (!item.configured) continue;
      const latLng = [item.latitude, item.longitude]; bounds.push(latLng);
      const marker = window.L.circleMarker(latLng, {
        radius: key(item) === place.value ? 10 : 6,
        color: key(item) === place.value ? '#b91c1c' : '#0369a1', fillOpacity: 0.85,
      }).bindTooltip(element('span', item.location)).addTo(markers);
      marker.on('click', () => { if (!publishing) { place.value = key(item); selectSource(); } });
    }
    if (source?.configured) {
      map.setView([source.latitude, source.longitude], 16, { animate: false });
    } else {
      if (bounds.length) map.fitBounds(bounds, { padding: [25, 25], maxZoom: 15, animate: false });
    }
    drawZone(true);
    map.invalidateSize();
  }
  function selectSource() { showLocation(); preview(); }

  async function loadOptions() {
    const request = ++optionsSequence, previous = place.value;
    loadingOptions = true; place.disabled = true; publish.disabled = true;
    try {
      const data = await authenticatedJSON(`/api/admin/alerts/options?limit=25&offset=${sourceOffset}`);
      if (!isAdmin() || request !== optionsSequence) return;
      if (sourceOffset && !data.reports.length) { sourceOffset = 0; return loadOptions(); }
      catalog = data; sources = new Map([...data.cameras, ...data.reports].map(item => [key(item), item]));
      place.replaceChildren(element('option', 'Selecciona el lugar afectado')); place.firstChild.value = '';
      for (const [label, items] of [['Cámaras', data.cameras], ['Reportes validados', data.reports]]) {
        const group = document.createElement('optgroup'); group.label = label;
        for (const item of items) {
          const reference = item.source_type === 'report' && item.location.startsWith('Cerca de ')
            ? ` · ${item.location.split(' (reporte')[0]}` : '';
          const date = item.source_type === 'report' && item.reviewed_at ? ` · ${localTime(item.reviewed_at)}` : '';
          const option = element('option', `${item.name}${reference}${date}${item.configured ? '' : ' · sin ubicación'}`);
          option.value = key(item); option.disabled = !item.configured; group.append(option);
        }
        place.append(group);
      }
      place.value = sources.has(previous) ? previous : '';
      const oldMessage = instruction.value;
      instruction.replaceChildren(...data.messages.map(item => { const option = element('option', item.label); option.value = item.id; return option; }));
      if (data.messages.some(item => item.id === oldMessage)) instruction.value = oldMessage;
      instruction.disabled = false; place.disabled = false;
      $('admin-alert-source-pages').hidden = data.total_reports <= 25;
      $('admin-source-page').textContent = data.total_reports ? `${sourceOffset + 1}–${Math.min(sourceOffset + data.reports.length, data.total_reports)} de ${data.total_reports} reportes` : 'Sin reportes validados';
      $('admin-source-previous').disabled = sourceOffset === 0; $('admin-source-next').disabled = sourceOffset + 25 >= data.total_reports;
      $('admin-alert-place-hint').textContent = data.total_reports
        ? 'Elige el punto y comprueba su ubicación en el mapa. Los reportes sin ubicación no se pueden seleccionar.'
        : 'Elige una cámara. Los reportes aparecerán aquí cuando estén validados.';
      selectSource();
    } catch (error) { if (isAdmin() && request === optionsSequence) status.textContent = error.message; }
    finally { if (request === optionsSequence) { loadingOptions = false; preview(); } }
  }

  function alertCard(item, history = false) {
    const card = element('article', undefined, 'site-admin-alert'); card.dataset.alertId = item.id;
    if (history) {
      const meta = element('div', undefined, 'alert-history-meta');
      meta.append(element('strong', item.title), element('span', item.active ? 'Activo' : 'Finalizado', `alert-history-state${item.active ? ' is-active' : ''}`)); card.append(meta);
    } else card.append(element('h3', item.title));
    card.append(element('p', item.location), element('p', item.message));
    if (Number.isInteger(item.radius_m)) card.append(element('p', `Zona de peligro: radio de ${item.radius_m} m`));
    if (Number.isFinite(item.latitude) && Number.isFinite(item.longitude)) card.append(alertMapLink(item));
    card.append(element('p', `Publicado: ${localTime(item.created_at)} (Lima)${history ? ` · ${item.published_by}` : ''}`, 'site-muted'));
    if (item.closed_at) card.append(element('p', `Finalizado: ${localTime(item.closed_at)} (Lima)${item.closed_by ? ` · ${item.closed_by}` : ''}`, 'site-muted'));
    if (item.active && !history) {
      const close = element('button', 'Finalizar aviso'); close.type = 'button';
      close.addEventListener('click', async () => {
        close.disabled = true;
        try {
          await authenticatedJSON(`/api/alerts/${item.id}/close`, { method: 'POST' });
          if (!isAdmin()) return;
          status.textContent = 'Aviso finalizado. Se conserva en el historial.'; refreshAlerts();
        } catch (error) { if (isAdmin()) { status.textContent = error.message; close.disabled = false; } }
      });
      card.append(close);
    }
    return card;
  }
  async function loadActive() {
    const request = ++activeSequence, container = $('admin-active-alerts');
    try {
      const data = await authenticatedJSON('/api/alerts');
      if (!isAdmin() || request !== activeSequence) return;
      container.replaceChildren(...data.items.map(item => alertCard(item)));
      if (!data.items.length) container.textContent = 'No hay avisos activos.';
    } catch (error) { if (isAdmin() && request === activeSequence) container.textContent = error.message; }
  }
  async function loadHistory() {
    const request = ++historySequence, container = $('admin-alert-history');
    try {
      const data = await authenticatedJSON(`/api/admin/alerts/history?limit=10&offset=${historyOffset}&status=${historyFilter.value}`);
      if (!isAdmin() || request !== historySequence) return;
      if (historyOffset && !data.items.length) { historyOffset = 0; return loadHistory(); }
      container.replaceChildren(...data.items.map(item => alertCard(item, true)));
      if (!data.items.length) container.textContent = 'No hay avisos en este historial.';
      $('admin-history-page').textContent = data.total ? `${historyOffset + 1}–${historyOffset + data.items.length} de ${data.total}` : 'Sin avisos';
      $('admin-history-previous').disabled = historyOffset === 0; $('admin-history-next').disabled = historyOffset + 10 >= data.total;
    } catch (error) { if (isAdmin() && request === historySequence) container.textContent = error.message; }
  }
  function refreshAlerts() { if (isAdmin()) { loadActive(); loadHistory(); } }

  kind.addEventListener('change', preview); instruction.addEventListener('change', preview);
  radius.addEventListener('input', () => { drawZone(true); preview(); });
  radius.addEventListener('change', () => { drawZone(true); preview(); });
  place.addEventListener('change', selectSource);
  form.addEventListener('submit', async event => {
    event.preventDefault(); const source = selected();
    if (publish.disabled || !isAdmin() || !source?.configured) return;
    const meters = radiusValue();
    publishing = true; place.disabled = kind.disabled = instruction.disabled = radius.disabled = true; preview(); status.textContent = 'Publicando aviso…';
    try {
      await authenticatedJSON('/api/alerts', { method: 'POST', body: JSON.stringify({ kind: kind.value, source_type: source.source_type, source_id: source.source_id, message_key: instruction.value, radius_m: meters }) });
      if (!isAdmin()) return;
      historyOffset = 0; historyFilter.value = 'active'; refreshAlerts();
      status.textContent = 'Aviso publicado y guardado en el historial.'; message('Aviso publicado. Se notificará a quienes tengan los avisos activados y una ubicación vigente dentro de la zona.');
    } catch (error) { if (isAdmin()) { status.textContent = error.message; loadOptions(); } }
    finally { publishing = false; if (isAdmin()) place.disabled = kind.disabled = instruction.disabled = radius.disabled = false; preview(); }
  });
  for (const [id, delta] of [['admin-source-previous', -25], ['admin-source-next', 25]]) $(id).addEventListener('click', () => { if (publishing) return; sourceOffset = Math.max(0, sourceOffset + delta); loadOptions(); });
  for (const [id, delta] of [['admin-history-previous', -10], ['admin-history-next', 10]]) $(id).addEventListener('click', () => { historyOffset = Math.max(0, historyOffset + delta); loadHistory(); });
  historyFilter.addEventListener('change', () => { historyOffset = 0; loadHistory(); });
  $('admin-refresh-history').addEventListener('click', () => { loadHistory(); if (!catalog) loadOptions(); });
  document.addEventListener('alerts-changed', refreshAlerts);
  document.addEventListener('reports-changed', () => { if (isAdmin() && !publishing) loadOptions(); });
  let hadSession = isAdmin();
  document.addEventListener('session-changed', () => {
    if (!isAdmin()) {
      ++optionsSequence; ++historySequence; ++activeSequence; catalog = null; sources.clear();
      form.reset(); place.replaceChildren(); instruction.replaceChildren();
      for (const id of ['admin-active-alerts', 'admin-alert-history', 'admin-history-page']) $(id).replaceChildren();
      markers?.clearLayers(); zone?.remove(); zone = null; mapStatus.hidden = true; mapStatus.textContent = ''; preview();
    } else if (!hadSession) { loadOptions(); refreshAlerts(); }
    hadSession = isAdmin();
  });
  loadOptions(); refreshAlerts();
}
