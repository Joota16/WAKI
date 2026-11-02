const snapshots = { level: null, discharge: [], weather: null };

export function getMeasurements() { return snapshots; }

export function publishMeasurements(metric, data) {
  snapshots[metric] = data;
  document.dispatchEvent(new Event('dashboard-measurements-updated'));
}

export function markMeasurementsUnavailable(metric) {
  const message = 'No se pudo actualizar WAKI. La lectura visible conserva su fecha.';
  const mark = data => data ? { ...data, status: 'error', message } : data;
  publishMeasurements(metric, metric === 'discharge' ? snapshots.discharge.map(mark) : mark(snapshots[metric]));
}

export const decimal = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 4 });
export const dayLabel = value => value.split('-').reverse().join('/');
export const timeLabel = value => new Intl.DateTimeFormat('es-PE', {
  timeZone: 'America/Lima', dateStyle: 'short', timeStyle: 'short', hourCycle: 'h23',
}).format(new Date(value));

export function thresholdText(reading) {
  if (reading?.discharge_m3s == null) return 'Sin caudal publicado';
  return {
    below_yellow: 'Por debajo del umbral amarillo', yellow: 'Umbral amarillo alcanzado',
    orange: 'Umbral naranja alcanzado', red: 'Umbral rojo alcanzado',
  }[reading.threshold_level] || 'Sin umbrales disponibles para esta lectura';
}

export function historyButton(metric, code) {
  const button = document.createElement('button');
  button.type = 'button'; button.dataset.historyKind = metric;
  button.dataset.historyStation = code;
  button.className = 'measurement-history-button';
  button.textContent = 'Ver histórico en tabla';
  return button;
}
