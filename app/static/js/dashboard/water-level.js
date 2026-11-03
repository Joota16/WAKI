import { publishMeasurements, markMeasurementsUnavailable } from './measurements.js';

const number = new Intl.NumberFormat('es-PE', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const dateLabel = value => value.split('-').reverse().join('/');
const dayNumber = value => Date.parse(`${value}T00:00:00Z`) / 86400000;
const svgNS = 'http://www.w3.org/2000/svg';

/** Esta tarjeta consume la caché local; las visitas nunca consultan SENAMHI. */
export function initWaterLevel() {
  const element = id => document.getElementById(id);
  const card = element('water-level-card');
  let river = null;
  let controller = null;
  let timer = null;
  let sequence = 0;

  function reset() {
    element('current-water-level').textContent = '—';
    element('water-level-station').textContent = 'Consultando estación…';
    element('water-level-date').textContent = '';
    element('water-level-checked').textContent = '';
    element('water-level-status').textContent = 'Cargando niveles publicados…';
    element('sparkline-path').removeAttribute('d');
    element('water-level-points').replaceChildren();
    for (const id of ['level-delta-text', 'water-level-chart', 'water-level-source', 'water-level-scope', 'water-level-retry']) element(id).hidden = true;
  }

  function drawChart(readings) {
    const values = readings.filter(item => item.level_m !== null);
    element('water-level-chart').hidden = !values.length;
    if (!values.length) return;
    const dates = readings.map(item => dayNumber(item.observed_date));
    const levels = values.map(item => item.level_m);
    const min = Math.min(...levels), max = Math.max(...levels);
    const range = Math.max(max - min, 0.02);
    const center = (max + min) / 2;
    const span = Math.max(dates.at(-1) - dates[0], 1);
    let path = '', previous = null;
    const dots = [];
    for (const reading of readings) {
      if (reading.level_m === null) { previous = null; continue; }
      const day = dayNumber(reading.observed_date);
      const x = 6 + (day - dates[0]) / span * 268;
      const y = 40 - (reading.level_m - center) / range * 60;
      const command = previous !== null && day - previous === 1 ? 'L' : 'M';
      path += `${command}${x.toFixed(2)},${y.toFixed(2)} `;
      previous = day;
      const dot = document.createElementNS(svgNS, 'circle');
      dot.setAttribute('cx', x); dot.setAttribute('cy', y);
      dot.setAttribute('r', '2.5'); dot.setAttribute('fill', '#0284c7');
      const title = document.createElementNS(svgNS, 'title');
      title.textContent = `${dateLabel(reading.observed_date)}: ${number.format(reading.level_m)} m`;
      dot.append(title); dots.push(dot);
    }
    element('sparkline-path').setAttribute('d', path.trim());
    element('water-level-points').replaceChildren(...dots);
    element('water-level-start-date').textContent = dateLabel(readings[0].observed_date);
    element('water-level-end-date').textContent = dateLabel(readings.at(-1).observed_date);
    element('water-level-chart-title').textContent = `Promedios diarios en metros, del ${dateLabel(readings[0].observed_date)} al ${dateLabel(readings.at(-1).observed_date)}. Mínimo ${number.format(min)} m; máximo ${number.format(max)} m.`;
  }

  function render(data) {
    element('water-level-station').textContent = data.station
      ? `${data.station.name} · código ${data.station.code}` : 'Sin estación conectada';
    element('water-level-scope').hidden = !data.station;
    element('water-level-source').hidden = !data.station;
    if (data.station) element('water-level-source').href = data.station.source_url;
    element('current-water-level').textContent = data.latest ? `${number.format(data.latest.level_m)} m` : '—';
    element('water-level-date').textContent = data.latest ? `Promedio del ${dateLabel(data.latest.observed_date)}` : '';
    element('water-level-status').textContent = data.message;
    element('water-level-status').className = ['stale', 'error'].includes(data.status) ? 'text-amber-800' : '';
    element('water-level-checked').textContent = data.last_success_at
      ? `Última consulta correcta: ${new Intl.DateTimeFormat('es-PE', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Lima' }).format(new Date(data.last_success_at))} (Lima).` : '';
    element('level-delta-text').hidden = data.previous_day_change_m === null;
    if (data.previous_day_change_m !== null) {
      const delta = data.previous_day_change_m;
      element('level-delta-text').textContent = `${delta > 0 ? '+' : ''}${number.format(delta)} m frente al promedio del día anterior.`;
    }
    drawChart(data.readings);
  }

  async function refresh() {
    clearTimeout(timer);
    controller?.abort();
    const request = new AbortController();
    controller = request;
    const current = ++sequence;
    let interval = 60000;
    card.setAttribute('aria-busy', 'true');
    element('water-level-retry').hidden = true;
    const timeout = setTimeout(() => request.abort(), 10000);
    try {
      const response = await fetch(`/api/hydrology/${river}`, { signal: request.signal, cache: 'no-store' });
      if (!response.ok) throw new Error('Consulta no disponible');
      const data = await response.json();
      if (current !== sequence) return;
      render(data);
      publishMeasurements('level', data);
      if (data.status === 'loading') interval = 5000;
    } catch {
      if (current !== sequence) return;
      markMeasurementsUnavailable('level');
      element('water-level-status').textContent = 'No se pudo consultar WAKI. Volveremos a intentarlo; cualquier lectura visible conserva su fecha de publicación.';
      element('water-level-retry').hidden = false;
    } finally {
      clearTimeout(timeout);
      if (current === sequence) {
        card.setAttribute('aria-busy', 'false');
        timer = setTimeout(() => { if (!document.hidden) refresh(); }, interval);
      }
    }
  }

  element('water-level-retry').addEventListener('click', refresh);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && river) refresh(); });
  return {
    selectRiver(key) {
      if (river === key) return;
      river = key;
      reset();
      refresh();
    },
  };
}
