import { decimal, dayLabel, timeLabel, thresholdText } from './measurements.js';

export function initMeasurementHistory() {
  const dialog = document.getElementById('measurement-history-dialog');
  const title = document.getElementById('measurement-history-title');
  const status = document.getElementById('measurement-history-status');
  const head = document.getElementById('measurement-history-head');
  const body = document.getElementById('measurement-history-body');
  const source = document.getElementById('measurement-history-source');
  const previous = document.getElementById('measurement-history-previous');
  const next = document.getElementById('measurement-history-next');
  const page = document.getElementById('measurement-history-page');
  const refresh = document.getElementById('measurement-history-refresh');
  let metric, code, offset = 0, sequence = 0, controller, trigger;
  const limit = 25;
  const metricNames = { level: 'Nivel', discharge: 'Caudal', weather: 'Precipitación y temperatura' };
  const cell = (row, tag, text) => { const node = document.createElement(tag); node.textContent = text; row.append(node); return node; };
  const value = number => number == null ? '—' : decimal.format(number);

  function table(items) {
    head.closest('table').dataset.metric = metric;
    const labels = {
      level: ['Fecha', 'Nivel promedio diario (m)'],
      discharge: ['Fecha y hora (Lima)', 'Caudal (m³/s)', 'Amarillo (m³/s)', 'Naranja (m³/s)', 'Rojo (m³/s)', 'Comparación con umbrales'],
      weather: ['Fecha', 'Precipitación (mm/día)', 'Temperatura máxima (°C)', 'Temperatura mínima (°C)'],
    }[metric];
    const header = document.createElement('tr');
    labels.forEach(text => { cell(header, 'th', text).scope = 'col'; });
    head.replaceChildren(header);
    body.replaceChildren(...items.map(item => {
      const row = document.createElement('tr');
      const values = metric === 'level' ? [dayLabel(item.observed_date), value(item.level_m)]
        : metric === 'weather' ? [dayLabel(item.observed_date), value(item.precipitation_mm), value(item.temperature_max_c), value(item.temperature_min_c)]
          : [timeLabel(item.observed_at), value(item.discharge_m3s), value(item.thresholds?.yellow_m3s),
            value(item.thresholds?.orange_m3s), value(item.thresholds?.red_m3s), thresholdText(item)];
      values.forEach(text => cell(row, 'td', text));
      if (metric === 'discharge') row.lastElementChild.dataset.thresholdLevel = item.threshold_level || '';
      return row;
    }));
  }

  async function load() {
    controller?.abort();
    const activeController = new AbortController(); controller = activeController;
    const request = ++sequence;
    const timeout = setTimeout(() => activeController.abort(), 10000);
    previous.disabled = next.disabled = refresh.disabled = true;
    body.replaceChildren(); head.replaceChildren(); page.textContent = '';
    status.textContent = 'Consultando historial…'; source.hidden = true;
    try {
      const params = new URLSearchParams({ limit, offset });
      if (code) params.set('station_code', code);
      const response = await fetch(`/api/hydrology/chillon/history/${metric}?${params}`, { signal: activeController.signal, cache: 'no-store' });
      if (!response.ok) throw Error('No se pudo consultar el historial. Pulsa Actualizar para volver a intentar.');
      const data = await response.json();
      if (request !== sequence || !dialog.open) return;
      if (offset && !data.items.length) { offset = Math.max(0, Math.ceil(data.total / limit) - 1) * limit; return load(); }
      title.textContent = `${metricNames[metric]} · ${data.station.name}`;
      source.href = data.station.source_url; source.hidden = false;
      table(data.items);
      status.textContent = data.total ? `Historial disponible · estación ${data.station.code}. Más recientes primero. «—» indica que no hay dato publicado.`
        : 'Todavía no hay registros históricos disponibles para esta estación.';
      page.textContent = data.total ? `${offset + 1}–${offset + data.items.length} de ${data.total}` : 'Sin registros';
      previous.disabled = offset === 0; next.disabled = offset + limit >= data.total;
    } catch (error) {
      if (request === sequence && dialog.open) status.textContent = error.name === 'AbortError'
        ? 'La consulta tardó demasiado. Pulsa Actualizar para volver a intentar.'
        : 'No se pudo consultar el historial. Pulsa Actualizar para volver a intentar.';
    } finally {
      clearTimeout(timeout);
      if (request === sequence) refresh.disabled = false;
    }
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-history-kind]');
    if (!button) return;
    trigger = button; metric = button.dataset.historyKind; code = button.dataset.historyStation || '';
    offset = 0; title.textContent = `Historial de ${metricNames[metric].toLocaleLowerCase('es')}`;
    if (!dialog.open) dialog.showModal();
    load();
  });
  previous.addEventListener('click', () => { offset = Math.max(0, offset - limit); load(); });
  next.addEventListener('click', () => { offset += limit; load(); });
  refresh.addEventListener('click', () => { offset = 0; load(); });
  dialog.addEventListener('close', () => {
    if (dialog.open) return; // Un cierre anterior no cancela una reapertura posterior.
    ++sequence; controller?.abort(); trigger?.focus({ preventScroll: true });
  });
}
