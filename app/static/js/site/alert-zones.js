import { element } from './utils.js';

export function hasAlertZone(item) {
  return Number.isFinite(item.latitude) && Math.abs(item.latitude) <= 90
    && Number.isFinite(item.longitude) && Math.abs(item.longitude) <= 180
    && Number.isInteger(item.radius_m) && item.radius_m >= 1 && item.radius_m <= 10000;
}

export function createAlertCircle(L, item) {
  const label = `Zona de peligro · radio ${item.radius_m} m`;
  const circle = L.circle([item.latitude, item.longitude], {
    radius: item.radius_m, color: '#dc2626', weight: 2, fillColor: '#ef4444', fillOpacity: 0.2,
    className: 'alert-danger-zone',
  }).bindTooltip(element('span', label));
  circle.on('add', () => {
    const path = circle.getElement();
    if (!path) return;
    path.setAttribute('aria-label', label);
    path.dataset.radiusM = String(item.radius_m);
    if (item.id) path.dataset.alertId = item.id;
  });
  return circle;
}
