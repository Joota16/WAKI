import { attentionStyle, RIVERS_DATA } from './data.js';
import { addHydrologicalStations } from './stations.js';
import { addRiverGeometry } from './river-geometry.js';
import { addAlertZones } from './alert-zones.js';

/** Leaflet y sus capas pertenecen a este módulo, sin variables globales. */
export function createRiverMap(onSelect) {
  const container = document.getElementById('map');
  if (!window.L) {
    document.getElementById('river-geometry-status').textContent = 'Mapa no disponible';
    container.classList.add('map-unavailable');
    container.textContent = 'No se pudo cargar el mapa. Comprueba tu conexión a Internet y recarga la página.';
    return null;
  }
  const L = window.L;
  const map = L.map(container, { center: [-12.0464, -77.0428], zoom: 11, zoomControl: false });
  const markers = {};
  let reportMarkers = [];
  let reports = [];
  let currentMode = 'risk';
  let pendingFocus = null;

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  function addRiverMarker(key, center) {
    const data = RIVERS_DATA[key];
    const style = attentionStyle(data.attentionLevel);
    const background = style.markerClass;
    const symbol = data.attentionLevel ? (data.attentionLevel === 'monitoring' ? '•' : '!') : '?';
    const pulse = data.attentionLevel === 'priority' ? '<div class="absolute w-8 h-8 rounded-full bg-red-500/40 pulse-ring"></div>' : '';
    const icon = L.divIcon({
      className: 'custom-river-marker',
      html: `<div class="relative flex items-center justify-center cursor-pointer -translate-x-1/2 -translate-y-1/2">
        ${pulse}<div class="w-6 h-6 rounded-full ${background} border-2 border-white shadow-lg flex items-center justify-center text-[10px] font-bold text-white transition-transform hover:scale-125">${symbol}</div>
      </div>`,
      iconSize: [24, 24], iconAnchor: [12, 12],
    });
    // Se usa texto, también para las etiquetas recibidas de la API.
    const popup = document.createElement('div');
    popup.className = 'p-3 text-left w-48 font-sans';
    const title = document.createElement('h4');
    title.className = 'font-bold text-xs sm:text-sm text-slate-900 leading-tight';
    title.textContent = data.name;
    const stretch = document.createElement('p'); stretch.className = 'text-[11px] text-slate-500 mt-0.5';
    stretch.textContent = data.stretch;
    const attention = document.createElement('p'); attention.className = 'mt-2 text-xs font-semibold text-slate-700';
    attention.textContent = 'Nivel de atención: ' + data.attentionLabel;
    const button = document.createElement('button'); button.type = 'button';
    button.className = 'mt-2.5 inline-flex items-center text-[11px] font-semibold text-sky-600 hover:underline';
    button.textContent = 'Ver detalles →';
    button.addEventListener('click', () => onSelect(key));
    popup.append(title, stretch, attention, button);
    if (markers[key]) map.removeLayer(markers[key]);
    markers[key] = L.marker(center, { icon })
      .bindPopup(popup, { offset: [0, -10] }).on('click', () => onSelect(key, false));
    if (currentMode === 'risk') markers[key].addTo(map);
  }
  function focusRiver(key) {
    const center = geometry.center(key);
    if (!center) { pendingFocus = key; return; }
    pendingFocus = null;
    map.flyTo(center, RIVERS_DATA[key].zoom, { duration: 1.2 });
    markers[key]?.openPopup();
  }
  const geometry = addRiverGeometry(L, map, onSelect, centers => {
    centers.forEach((center, key) => addRiverMarker(key, center));
    if (pendingFocus && currentMode === 'risk') focusRiver(pendingFocus);
  });
  const stations = addHydrologicalStations(L, map);
  stations.showAll({ animate: false });
  const alertZones = addAlertZones(L, map);
  requestAnimationFrame(() => map.invalidateSize());

  function drawReports() {
    reportMarkers.forEach(marker => map.removeLayer(marker));
    reportMarkers = [];
    for (const report of reports) {
      if (report.latitude === null || report.longitude === null) continue;
      const popup = document.createElement('div');
      popup.className = 'p-3 text-xs';
      const title = document.createElement('strong');
      title.textContent = `Reporte ${report.id.slice(0, 8)}`;
      const observations = document.createElement('p');
      observations.className = 'mt-1 text-slate-600';
      observations.textContent = report.observations.slice(0, 160);
      const link = document.createElement('a');
      link.href = report.detail_url;
      link.className = 'inline-block mt-2 text-sky-600 font-semibold underline';
      link.textContent = 'Ver reporte y fotografías';
      popup.append(title, observations, link);
      const icon = L.divIcon({
        className: 'citizen-marker',
        html: '<div class="bg-sky-600 border-2 border-white rounded-full w-6 h-6 flex items-center justify-center text-white text-xs font-bold shadow-md">💬</div>',
        iconSize: [24, 24], iconAnchor: [12, 12],
      });
      reportMarkers.push(L.marker([report.latitude, report.longitude], { icon }).addTo(map).bindPopup(popup));
    }
  }

  return {
    selectRiver(key, fly = true) {
      geometry.select(key);
      if (fly && currentMode !== 'reports') focusRiver(key);
    },
    recenter: () => map.flyTo([-12.0464, -77.0428], 11, { duration: 1 }),
    showStations: () => stations.showAll(),
    showAlertZones: () => alertZones.focusAll(),
    focusStation: id => stations.focus(id),
    updateAttention(key) {
      geometry.refresh();
      const center = geometry.center(key);
      if (!center) return;
      const opened = markers[key]?.isPopupOpen();
      addRiverMarker(key, center);
      if (opened && currentMode === 'risk') markers[key].openPopup();
    },
    zoomIn: () => map.zoomIn(),
    zoomOut: () => map.zoomOut(),
    setReports(items) {
      reports = items;
      if (currentMode === 'reports') drawReports();
    },
    setMode(mode) {
      if (!['risk', 'reports'].includes(mode)) return;
      currentMode = mode;
      pendingFocus = null;
      geometry.setMode(mode);
      reportMarkers.forEach(marker => map.removeLayer(marker));
      reportMarkers = [];
      for (const marker of Object.values(markers)) {
        if (mode === 'reports') map.removeLayer(marker);
        else if (!map.hasLayer(marker)) marker.addTo(map);
      }
      document.getElementById('map-risk-legend').classList.toggle('hidden', mode === 'reports');
      if (mode === 'reports') {
        drawReports();
        if (reportMarkers.length) map.fitBounds(L.featureGroup(reportMarkers).getBounds(), { padding: [45, 100], maxZoom: 14 });
      }
    },
  };
}

