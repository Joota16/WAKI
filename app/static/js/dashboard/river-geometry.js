import { attentionStyle, RIVERS_DATA } from './data.js';

/** Cauce cartografiado local: no se inventan segmentos si falta la geometría. */
export function addRiverGeometry(L, map, onSelect, onLoaded) {
  const layers = new Map();
  const centers = new Map();
  const status = document.getElementById('river-geometry-status');
  const retry = document.getElementById('retry-river-geometry');
  let selected = 'chillon';
  let mode = 'risk';
  let loading = false;

  function style(id) {
    const active = selected === id;
    return { color: attentionStyle(RIVERS_DATA[id].attentionLevel).color, weight: active ? 6 : 4,
      opacity: mode === 'reports' ? 0.2 : active ? 1 : 0.6,
      lineCap: 'round', lineJoin: 'round', smoothFactor: 0,
      className: `river-course river-course-${id}` };
  }

  function updateStyles() {
    layers.forEach((layer, id) => layer.setStyle(style(id)));
  }

  function validate(collection) {
    if (collection.type !== 'FeatureCollection' || collection.features?.length !== Object.keys(RIVERS_DATA).length) throw new Error('Datos de cauces incompletos.');
    const ids = new Set();
    for (const feature of collection.features) {
      const id = feature.properties?.id;
      if (!RIVERS_DATA[id] || ids.has(id) || feature.geometry?.type !== 'MultiLineString') throw new Error('Cauce no reconocido.');
      ids.add(id);
      const lines = feature.geometry.coordinates;
      if (!Array.isArray(lines) || !lines.length) throw new Error('Geometría vacía.');
      for (const line of lines) {
        if (!Array.isArray(line) || line.length < 2) throw new Error('Tramo incompleto.');
        for (const point of line) {
          if (point.length !== 2 || !point.every(Number.isFinite)
            || point[0] <= -78 || point[0] >= -75 || point[1] <= -13 || point[1] >= -10) throw new Error('Coordenadas inválidas.');
        }
      }
      const center = feature.properties.view_center;
      if (!Array.isArray(center) || center.length !== 2 || !center.every(Number.isFinite)
        || !lines.some(line => line.some(point => point[0] === center[0] && point[1] === center[1]))) throw new Error('Foco fuera del cauce.');
    }
  }

  async function load() {
    if (loading) return;
    loading = true;
    retry.hidden = true;
    status.textContent = 'Cargando cauces…';
    try {
      const response = await fetch('/static/data/rivers.geojson');
      if (!response.ok) throw new Error('No se pudo cargar la cartografía.');
      const collection = await response.json();
      validate(collection);
      layers.forEach(layer => map.removeLayer(layer));
      layers.clear();
      centers.clear();
      for (const feature of collection.features) {
        const id = feature.properties.id;
        const layer = L.geoJSON(feature, { style: style(id) }).addTo(map);
        layer.on('click', () => onSelect(id));
        layers.set(id, layer);
        const [longitude, latitude] = feature.properties.view_center;
        centers.set(id, L.latLng(latitude, longitude));
      }
      status.textContent = 'Cauces OSM';
      status.title = `Cartografía de OpenStreetMap · ${collection.source_timestamp || ''}`;
      onLoaded(centers);
    } catch {
      status.textContent = 'Cauces no disponibles';
      status.title = 'No se pudo cargar el trazado cartográfico de los ríos.';
      retry.hidden = false;
    } finally {
      loading = false;
    }
  }

  retry.addEventListener('click', load);
  load();
  return {
    select(id) { selected = id; updateStyles(); },
    setMode(value) { mode = value; updateStyles(); },
    center(id) { return centers.get(id); },
    refresh: updateStyles,
  };
}
