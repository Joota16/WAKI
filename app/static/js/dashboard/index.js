import { RIVERS_DATA } from './data.js';
import { createRiverMap } from './map.js';
import { renderRiver, switchTab } from './view.js';
import { initRecentReports } from './reports.js';
import { HYDROLOGICAL_STATIONS } from './stations-data.js';
import { initWaterLevel } from './water-level.js';
import { initDischarge } from './discharge.js';
import { initWeather } from './weather.js';
import { initCamera } from './camera.js';
import { initAnalyses } from './analyses.js';
import { initAttention } from './attention.js';

const waterLevel = initWaterLevel();
const discharge = initDischarge();
const weather = initWeather();
const camera = initCamera();
const analyses = initAnalyses();
const riverMap = createRiverMap(selectRiver);
initAttention(riverMap);

function selectRiver(key, fly = true) {
  if (!RIVERS_DATA[key]) return;
  renderRiver(key, RIVERS_DATA[key]);
  waterLevel.selectRiver(key);
  discharge.selectRiver(key);
  weather.selectRiver(key);
  camera.selectRiver(key);
  analyses.selectRiver(key);
  riverMap?.selectRiver(key, fly);
}

document.querySelectorAll('[data-river]').forEach(row => {
  row.addEventListener('click', () => selectRiver(row.dataset.river));
  row.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      selectRiver(row.dataset.river);
    }
  });
});

document.querySelectorAll('[data-tab]').forEach(button => {
  button.addEventListener('click', () => switchTab(button.dataset.tab));
});

const mapActions = {
  recenter: () => riverMap?.recenter(),
  stations: () => riverMap?.showStations(),
  'zoom-in': () => riverMap?.zoomIn(),
  'zoom-out': () => riverMap?.zoomOut(),
};
document.querySelectorAll('[data-map-action]').forEach(button => {
  button.addEventListener('click', mapActions[button.dataset.mapAction]);
});
document.querySelectorAll('[data-map-mode]').forEach(button => {
  button.addEventListener('click', () => {
    const mode = button.dataset.mapMode;
    riverMap?.setMode(mode);
    document.querySelectorAll('[data-map-mode]').forEach(item => {
      const active = item === button;
      item.setAttribute('aria-pressed', String(active));
      item.className = active
        ? 'px-3 py-1.5 rounded-lg bg-sky-600 text-white font-medium shadow-xs transition-colors'
        : 'px-3 py-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors';
    });
  });
});

const search = document.getElementById('global-search');
const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es');
search.addEventListener('input', () => {
  const term = normalize(search.value).trim();
  if (!term) return;
  const match = Object.entries(RIVERS_DATA).find(([, river]) =>
    [river.name, river.location, river.stretch].some(value => normalize(value).includes(term)),
  );
  if (match) {
    selectRiver(match[0]);
    return;
  }
  const station = HYDROLOGICAL_STATIONS.find(item => normalize(item.name).includes(term));
  if (station) riverMap?.focusStation(station.id);
});
selectRiver('chillon', false);
switchTab(location.hash === '#imagenes' ? 'imagenes' : 'resumen');
initRecentReports(riverMap);
if (search.value.trim()) search.dispatchEvent(new Event('input'));
