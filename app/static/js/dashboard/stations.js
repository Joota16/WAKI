import { HYDROLOGICAL_STATIONS } from './stations-data.js';
import { getMeasurements, decimal, dayLabel, timeLabel, thresholdText } from './measurements.js';

/** Capa de estaciones independiente de los trazados y reportes ciudadanos. */
export function addHydrologicalStations(L, map) {
  const layer = L.featureGroup().addTo(map);
  const markers = new Map();
  const measurementPanels = new Map();

  function text(parent, tag, content, className = '') {
    const node = document.createElement(tag); node.textContent = content;
    node.className = className; parent.append(node); return node;
  }

  function section(parent, title, data) {
    const result = document.createElement('section'); result.className = 'station-measurement';
    text(result, 'h4', title);
    if (data.message && ['error', 'stale'].includes(data.status)) text(result, 'p', data.message, 'station-measurement-warning');
    parent.append(result);
    return result;
  }

  function updateMeasurements() {
    const { level, discharge, weather } = getMeasurements();
    for (const station of HYDROLOGICAL_STATIONS) {
      const panel = measurementPanels.get(station.id); panel.replaceChildren();
      if (station.id === 'malecon-chillon') {
        text(panel, 'p', 'Punto de cámara. Sin mediciones SENAMHI de nivel, caudal o precipitación asociadas a este punto.', 'station-measurement-note');
        continue;
      }
      const flow = discharge.find(item => item.station.id === station.id);
      if (flow) {
        const group = section(panel, 'Último caudal publicado', flow);
        const reading = flow.latest;
        text(group, 'p', reading ? `${decimal.format(reading.discharge_m3s)} m³/s · ${timeLabel(reading.observed_at)} (Lima)` : 'Sin caudal publicado.');
        const state = text(group, 'p', thresholdText(reading), 'discharge-threshold-status');
        state.dataset.thresholdLevel = reading?.threshold_level || '';
      }
      if (station.id === 'puente-magdalena' && level?.station?.code === '111151') {
        const group = section(panel, 'Último nivel promedio diario', level);
        text(group, 'p', level.latest ? `${decimal.format(level.latest.level_m)} m · ${dayLabel(level.latest.observed_date)}` : 'Sin nivel publicado.');
      }
      if (station.id === 'obrajillo' && weather?.station?.code === '156133') {
        const group = section(panel, 'Datos meteorológicos de Obrajillo', weather);
        for (const [label, key, unit] of [['Precipitación', 'latest_precipitation', 'mm/día'],
          ['Temperatura máxima', 'latest_temperature_max', '°C'], ['Temperatura mínima', 'latest_temperature_min', '°C']]) {
          const reading = weather[key];
          text(group, 'p', reading ? `${label}: ${decimal.format(reading.value)} ${unit} · ${dayLabel(reading.observed_date)}` : `${label}: sin dato publicado.`);
        }
      }
      if (!panel.childElementCount) text(panel, 'p', 'Consultando las últimas mediciones de esta estación…', 'station-measurement-note');
      if (markers.get(station.id).isPopupOpen()) markers.get(station.id).getPopup().update();
    }
  }

  for (const station of HYDROLOGICAL_STATIONS) {
    const popup = document.createElement('div');
    popup.className = 'hydro-station-popup';
    const title = document.createElement('h3');
    title.textContent = station.name;
    const type = document.createElement('p');
    type.textContent = station.id === 'malecon-chillon' ? 'Punto de cámara' : 'Estación hidrológica';
    const coordinates = document.createElement('p');
    coordinates.className = 'hydro-station-coordinates';
    coordinates.textContent = `Latitud: ${station.latLng[0]} · Longitud: ${station.latLng[1]}`;
    const measurements = document.createElement('div');
    measurements.className = 'station-measurements'; measurementPanels.set(station.id, measurements);
    popup.append(title, type, coordinates, measurements);

    const marker = L.marker(station.latLng, {
      title: station.name,
      zIndexOffset: 600,
      icon: L.divIcon({
        className: 'hydro-station-marker',
        html: '<span class="hydro-station-symbol" aria-hidden="true">EH</span>',
        iconSize: [32, 32], iconAnchor: [16, 16], popupAnchor: [0, -16],
      }),
    }).addTo(layer).bindPopup(popup, { maxWidth: 290, maxHeight: 370 }).bindTooltip(station.name, {
      permanent: true, direction: 'top', offset: [0, -18], className: 'hydro-station-label',
    });
    const icon = marker.getElement();
    icon.dataset.stationId = station.id;
    icon.setAttribute('aria-label', `Estación hidrológica ${station.name}`);
    markers.set(station.id, marker);
  }
  document.addEventListener('dashboard-measurements-updated', updateMeasurements);
  updateMeasurements();
  map.on('unload', () => document.removeEventListener('dashboard-measurements-updated', updateMeasurements));

  return {
    showAll(options = {}) {
      map.fitBounds(layer.getBounds(), {
        paddingTopLeft: [72, 125], paddingBottomRight: [72, 180], maxZoom: 13, ...options,
      });
    },
    focus(id) {
      const marker = markers.get(id);
      if (!marker) return;
      map.setView(marker.getLatLng(), 13);
      marker.openPopup();
    },
  };
}
