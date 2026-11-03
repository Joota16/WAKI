import { publishMeasurements, markMeasurementsUnavailable, thresholdText, decimal } from './measurements.js';

const number = new Intl.NumberFormat('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
const timestamp = new Intl.DateTimeFormat('es-PE', {
  timeZone: 'America/Lima', day: '2-digit', month: '2-digit', year: 'numeric',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});
const shortTimestamp = new Intl.DateTimeFormat('es-PE', {
  timeZone: 'America/Lima', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});
const svgNS = 'http://www.w3.org/2000/svg';

/** Dos estaciones de Chillón; consulta SQLite a través de WAKI, nunca SENAMHI. */
export function initDischarge() {
  const cards = [...document.querySelectorAll('[data-discharge-station]')];
  const group = document.getElementById('discharge-cards');
  const empty = document.getElementById('discharge-empty');
  const field = (card, key) => card.querySelector(`[data-field="${key}"]`);
  let river = null, sequence = 0, controller = null, timer = null;

  function drawChart(card, data) {
    const readings = data.readings;
    const valid = readings.filter(item => item.discharge_m3s !== null);
    field(card, 'chart').hidden = !valid.length;
    if (!valid.length) return;
    const values = valid.map(item => item.discharge_m3s);
    const min = Math.min(...values), max = Math.max(...values);
    const center = (max + min) / 2, range = Math.max(max - min, 0.01);
    const start = Date.parse(readings[0].observed_at), end = Date.parse(readings.at(-1).observed_at);
    const span = Math.max(end - start, 1);
    let path = '', previous = null;
    const dots = [];
    for (const reading of readings) {
      if (reading.discharge_m3s === null) { previous = null; continue; }
      const time = Date.parse(reading.observed_at);
      const x = 6 + (time - start) / span * 268;
      const y = 40 - (reading.discharge_m3s - center) / range * 60;
      const connected = previous !== null && time - previous <= data.station.chart_gap_seconds * 1000;
      path += `${connected ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)} `;
      previous = time;
      const dot = document.createElementNS(svgNS, 'circle');
      dot.setAttribute('cx', x); dot.setAttribute('cy', y);
      dot.setAttribute('r', '1.8'); dot.setAttribute('fill', '#0284c7');
      const title = document.createElementNS(svgNS, 'title');
      title.textContent = `${timestamp.format(new Date(time))} (Lima): ${number.format(reading.discharge_m3s)} m³/s`;
      dot.append(title); dots.push(dot);
    }
    field(card, 'chart-path').setAttribute('d', path.trim());
    field(card, 'chart-points').replaceChildren(...dots);
    field(card, 'start-date').textContent = shortTimestamp.format(new Date(start));
    field(card, 'end-date').textContent = shortTimestamp.format(new Date(end));
    field(card, 'chart-title').textContent = `Caudal de ${data.station.name}, en m³/s. Mínimo ${number.format(min)}; máximo ${number.format(max)}. Las horas se muestran en Lima.`;
  }

  function render(card, data) {
    field(card, 'value').textContent = data.latest ? `${number.format(data.latest.discharge_m3s)} m³/s` : '—';
    field(card, 'observed-at').textContent = data.latest ? `${timestamp.format(new Date(data.latest.observed_at))} (Lima)` : '';
    field(card, 'status').textContent = data.message;
    field(card, 'status').className = ['error', 'stale'].includes(data.status) ? 'text-[11px] text-amber-800' : 'text-[11px] text-slate-600';
    field(card, 'checked-at').textContent = data.last_success_at ? `Consultado: ${timestamp.format(new Date(data.last_success_at))} (Lima).` : '';
    field(card, 'source').href = data.source_url;
    const reading = data.latest;
    field(card, 'value').dataset.thresholdLevel = reading?.threshold_level || '';
    field(card, 'threshold-status').textContent = thresholdText(reading);
    field(card, 'threshold-status').dataset.thresholdLevel = reading?.threshold_level || '';
    field(card, 'thresholds').hidden = !reading?.thresholds;
    field(card, 'threshold-values').replaceChildren();
    if (reading?.thresholds) {
      for (const [key, label] of [['yellow', 'Amarillo'], ['orange', 'Naranja'], ['red', 'Rojo']]) {
        const chip = document.createElement('span'); chip.dataset.thresholdLevel = key;
        chip.textContent = `${label} ≥ ${decimal.format(reading.thresholds[key + '_m3s'])}`;
        field(card, 'threshold-values').append(chip);
      }
    }
    drawChart(card, data);
  }

  async function refresh() {
    clearTimeout(timer);
    controller?.abort();
    const request = new AbortController();
    controller = request;
    const current = ++sequence;
    const timeout = setTimeout(() => request.abort(), 10000);
    let interval = 60000;
    cards.forEach(card => {
      card.setAttribute('aria-busy', 'true');
      field(card, 'retry').hidden = true;
    });
    try {
      const response = await fetch(`/api/hydrology/${river}/discharge`, { signal: request.signal, cache: 'no-store' });
      if (!response.ok) throw new Error('Consulta de caudal no disponible');
      const data = await response.json();
      if (current !== sequence) return;
      for (const card of cards) {
        const reading = data.find(item => item.station.id === card.dataset.dischargeStation);
        if (!reading) throw new Error('Falta una estación de caudal');
        render(card, reading);
      }
      publishMeasurements('discharge', data);
      if (data.some(item => item.status === 'loading')) interval = 5000;
    } catch {
      if (current !== sequence) return;
      markMeasurementsUnavailable('discharge');
      cards.forEach(card => {
        field(card, 'status').textContent = 'No se pudo consultar WAKI. Cualquier lectura visible conserva su fecha de publicación.';
        field(card, 'retry').hidden = false;
      });
    } finally {
      clearTimeout(timeout);
      if (current === sequence) {
        cards.forEach(card => card.setAttribute('aria-busy', 'false'));
        timer = setTimeout(() => { if (!document.hidden && river === 'chillon') refresh(); }, interval);
      }
    }
  }

  cards.forEach(card => field(card, 'retry').addEventListener('click', refresh));
  document.addEventListener('visibilitychange', () => { if (!document.hidden && river === 'chillon') refresh(); });
  return {
    selectRiver(key) {
      if (key === river) return;
      river = key;
      clearTimeout(timer);
      controller?.abort();
      sequence++;
      group.classList.toggle('hidden', river !== 'chillon');
      empty.hidden = river === 'chillon';
      if (river === 'chillon') refresh();
    },
  };
}
