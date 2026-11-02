import { publishMeasurements, markMeasurementsUnavailable } from './measurements.js';

const number = new Intl.NumberFormat('es-PE', { minimumFractionDigits: 1, maximumFractionDigits: 2 });
const dateLabel = day => day.split('-').reverse().join('/');
const dayNumber = day => Date.parse(`${day}T00:00:00Z`) / 86400000;
const svgNS = 'http://www.w3.org/2000/svg';

/** Datos meteorológicos independientes: null nunca se transforma en cero. */
export function initWeather() {
  const element = id => document.getElementById(id);
  const card = element('weather-card');
  let river = null, sequence = 0, controller = null, timer = null;

  function node(tag, attributes = {}) {
    const result = document.createElementNS(svgNS, tag);
    for (const [key, value] of Object.entries(attributes)) result.setAttribute(key, value);
    return result;
  }

  function chart(readings, metrics, bars, svgId, containerId, unit) {
    const values = readings.flatMap(item => metrics.map(metric => item[metric.key])).filter(value => value !== null);
    const svg = element(svgId);
    svg.replaceChildren();
    element(containerId).hidden = !values.length;
    if (!values.length) return;
    const min = Math.min(...values), max = Math.max(...values);
    const start = dayNumber(readings[0].observed_date), end = dayNumber(readings.at(-1).observed_date);
    const span = Math.max(end - start, 1);
    const title = node('title');
    title.textContent = `${dateLabel(readings[0].observed_date)} a ${dateLabel(readings.at(-1).observed_date)}. Mínimo ${number.format(min)}; máximo ${number.format(max)} ${unit}.`;
    svg.append(title);
    for (const metric of metrics) {
      let path = '', previous = null;
      for (const reading of readings) {
        const value = reading[metric.key];
        if (value === null) { previous = null; continue; }
        const day = dayNumber(reading.observed_date);
        const x = 6 + (day - start) / span * 268;
        const y = bars ? 74 - value / Math.max(max, 1) * 64 : 40 - (value - (min + max) / 2) / Math.max(max - min, 1) * 60;
        const mark = bars
          ? node('rect', { x: x - 2, y, width: 4, height: Math.max(74 - y, 1), fill: metric.color })
          : node('circle', { cx: x, cy: y, r: 2, fill: metric.color });
        const tooltip = node('title');
        tooltip.textContent = `${metric.label} · ${dateLabel(reading.observed_date)}: ${number.format(value)} ${unit}`;
        mark.append(tooltip); svg.append(mark);
        path += `${previous !== null && day - previous === 1 ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)} `;
        previous = day;
      }
      if (!bars) svg.prepend(node('path', { d: path.trim(), fill: 'none', stroke: metric.color, 'stroke-width': 1.5 }));
    }
  }

  function metric(id, reading, unit) {
    element(id).textContent = reading ? `${number.format(reading.value)} ${unit}` : '—';
    element(`${id}-date`).textContent = reading ? `Dato del ${dateLabel(reading.observed_date)}` : 'Sin datos publicados';
  }

  function render(data) {
    if (!data.station || data.station.code !== card.dataset.weatherStation) throw new Error('Estación meteorológica inesperada');
    metric('weather-precipitation', data.latest_precipitation, 'mm/día');
    metric('weather-temperature-max', data.latest_temperature_max, '°C');
    metric('weather-temperature-min', data.latest_temperature_min, '°C');
    chart(data.readings, [{ key: 'precipitation_mm', color: '#0284c7', label: 'Precipitación' }], true, 'weather-rain-svg', 'weather-rain-chart', 'mm/día');
    chart(data.readings, [
      { key: 'temperature_max_c', color: '#dc2626', label: 'Temperatura máxima' },
      { key: 'temperature_min_c', color: '#2563eb', label: 'Temperatura mínima' },
    ], false, 'weather-temperature-svg', 'weather-temperature-chart', '°C');
    element('weather-period').textContent = data.readings.length
      ? `Serie publicada: ${dateLabel(data.readings[0].observed_date)} – ${dateLabel(data.readings.at(-1).observed_date)}` : '';
    element('weather-status').textContent = data.message;
    element('weather-status').hidden = !data.message;
    element('weather-status').className = ['stale', 'error'].includes(data.status) ? 'text-[11px] text-amber-800' : 'text-[11px] text-slate-600';
    element('weather-checked').textContent = data.last_success_at
      ? `Consultado: ${new Intl.DateTimeFormat('es-PE', { timeZone: 'America/Lima', dateStyle: 'short', timeStyle: 'short' }).format(new Date(data.last_success_at))} (Lima).` : '';
    element('weather-source').href = data.station.source_url;
  }

  async function refresh() {
    clearTimeout(timer);
    controller?.abort();
    const request = new AbortController();
    controller = request;
    const current = ++sequence;
    const timeout = setTimeout(() => request.abort(), 10000);
    let interval = 60000;
    card.setAttribute('aria-busy', 'true');
    element('weather-retry').hidden = true;
    try {
      const response = await fetch(`/api/hydrology/${river}/weather`, { signal: request.signal, cache: 'no-store' });
      if (!response.ok) throw new Error('Meteorología no disponible');
      const data = await response.json();
      if (current !== sequence) return;
      render(data);
      publishMeasurements('weather', data);
      if (data.status === 'loading') interval = 5000;
    } catch {
      if (current !== sequence) return;
      markMeasurementsUnavailable('weather');
      element('weather-status').textContent = 'No se pudo consultar WAKI. Las lecturas visibles conservan sus fechas de publicación.';
      element('weather-status').hidden = false;
      element('weather-retry').hidden = false;
    } finally {
      clearTimeout(timeout);
      if (current === sequence) {
        card.setAttribute('aria-busy', 'false');
        timer = setTimeout(() => { if (!document.hidden && river === 'chillon') refresh(); }, interval);
      }
    }
  }

  element('weather-retry').addEventListener('click', refresh);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && river === 'chillon') refresh(); });
  return {
    selectRiver(key) {
      if (river === key) return;
      river = key;
      clearTimeout(timer); controller?.abort(); sequence++;
      card.classList.toggle('hidden', river !== 'chillon');
      element('weather-empty').hidden = river === 'chillon';
      if (river === 'chillon') refresh();
    },
  };
}
