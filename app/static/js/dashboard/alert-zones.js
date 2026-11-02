import { getActiveAlerts } from '../site/alerts.js';
import { createAlertCircle, hasAlertZone } from '../site/alert-zones.js';
import { element } from '../site/utils.js';

export function addAlertZones(L, map) {
  const layer = L.layerGroup().addTo(map), circles = new Map();
  const legend = document.getElementById('map-alert-zones');
  const requested = new URL(location.href).searchParams.get('aviso');
  let signature = '', focused = false;

  function update(items) {
    const active = items.filter(item => item.active && hasAlertZone(item));
    const current = JSON.stringify(active);
    if (signature === current) return;
    signature = current; layer.clearLayers(); circles.clear();
    for (const item of active) {
      const circle = createAlertCircle(L, item);
      const popup = element('div', undefined, 'alert-zone-popup');
      popup.append(element('strong', item.title), element('p', item.location),
        element('p', `Zona de peligro: radio de ${item.radius_m} m`), element('p', item.message));
      circle.bindPopup(popup).addTo(layer); circles.set(item.id, circle);
    }
    legend.hidden = active.length === 0;
    document.getElementById('map-alert-zones-count').textContent = `${active.length} ${active.length === 1 ? 'aviso activo' : 'avisos activos'}`;
    if (!focused && requested && circles.has(requested)) {
      focused = true;
      const circle = circles.get(requested);
      map.fitBounds(circle.getBounds(), { padding: [40, 40], maxZoom: 18 });
      circle.openPopup();
    }
  }
  document.addEventListener('active-alerts-updated', event => update(event.detail));
  update(getActiveAlerts());
  return {
    focusAll() {
      if (!circles.size) return;
      map.fitBounds(L.featureGroup([...circles.values()]).getBounds(), { padding: [40, 40], maxZoom: 18 });
    },
  };
}
