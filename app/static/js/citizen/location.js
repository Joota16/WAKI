/** Ubicación proporcionada por el navegador o introducida por el ciudadano. */
export function initLocation() {
  const form = document.getElementById('citizenReportForm');
  const button = document.getElementById('btnGpsEasy');
  const latitude = document.getElementById('hiddenLat');
  const longitude = document.getElementById('hiddenLon');
  const error = document.getElementById('locationError');
  const badge = document.getElementById('gpsBadge');
  const accuracy = document.getElementById('gpsAccuracy');
  const warning = document.getElementById('locationAccuracyWarning');
  const distance = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 1 });
  const formatAccuracy = meters => meters >= 1000
    ? `${distance.format(meters / 1000)} km` : `${Math.round(meters)} m`;
  let pending = false;

  function showError(message) { error.textContent = message; error.hidden = !message; }
  function render() {
    const lat = Number(latitude.value);
    const lon = Number(longitude.value);
    const valid = latitude.value !== '' && longitude.value !== '' && Number.isFinite(lat) && Number.isFinite(lon)
      && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
    const meters = Number(accuracy.value);
    const browserLocation = accuracy.value !== '' && Number.isFinite(meters) && meters > 0;
    const lowAccuracy = browserLocation && meters > 500;
    const precision = browserLocation ? ` · radio de precisión aproximado: ${formatAccuracy(meters)}` : '';
    document.getElementById('gpsCoordsText').textContent = valid
      ? `${lat.toFixed(6)}, ${lon.toFixed(6)}${precision}`
      : 'Sin coordenadas.';
    document.getElementById('summaryCoords').textContent = valid ? `${lat.toFixed(6)}, ${lon.toFixed(6)}` : 'Sin coordenadas';
    badge.textContent = valid
      ? (browserLocation ? (lowAccuracy ? 'Ubicación aproximada · Baja precisión' : 'Ubicación del navegador') : 'Ubicación manual')
      : 'Sin coordenadas';
    warning.hidden = !valid || !lowAccuracy;
    warning.textContent = valid && lowAccuracy
      ? `El navegador indica un radio de precisión de ${formatAccuracy(meters)}. El punto puede señalar otro barrio. Compruébalo en el mapa; si no corresponde al lugar observado, corrige las coordenadas manualmente o prueba desde un celular con ubicación precisa.`
      : '';
    const link = document.getElementById('locationMapLink');
    link.hidden = !valid;
    if (valid) link.href = `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=16/${lat}/${lon}`;
    return valid;
  }
  function finish() {
    pending = false;
    button.disabled = false;
    button.textContent = 'Usar mi ubicación actual';
  }
  button.addEventListener('click', () => {
    showError('');
    if (!window.isSecureContext) {
      showError('Para obtener tu ubicación, abre WAKI con HTTPS o desde localhost. También puedes indicar las coordenadas manualmente.');
      return;
    }
    if (!navigator.geolocation) {
      showError('Este navegador no permite obtener la ubicación. Puedes introducir las coordenadas manualmente.');
      return;
    }
    pending = true;
    button.disabled = true;
    button.textContent = 'Obteniendo ubicación…';
    badge.textContent = 'Esperando permiso o ubicación del navegador';
    navigator.geolocation.getCurrentPosition(position => {
      const { latitude: lat, longitude: lon, accuracy: meters } = position.coords;
      latitude.value = lat.toFixed(6);
      longitude.value = lon.toFixed(6);
      accuracy.value = Number.isFinite(meters) && meters > 0 ? String(meters) : '';
      render();
      finish();
      form.dispatchEvent(new Event('change', { bubbles: true }));
    }, failure => {
      const messages = {
        1: 'No diste permiso para usar tu ubicación. Puedes habilitarlo en el navegador o escribir las coordenadas.',
        2: 'No se pudo determinar tu ubicación. Inténtalo de nuevo o indica el lugar manualmente.',
        3: 'La ubicación tardó demasiado. Inténtalo de nuevo o indica el lugar manualmente.',
      };
      render();
      showError(messages[failure.code] || 'No se pudo obtener la ubicación. Puedes indicar el lugar manualmente.');
      finish();
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  });
  for (const input of [latitude, longitude]) {
    input.addEventListener('input', () => { accuracy.value = ''; showError(''); render(); });
  }
  document.getElementById('btnClearLocation').addEventListener('click', () => {
    latitude.value = longitude.value = accuracy.value = '';
    showError(''); render();
    form.dispatchEvent(new Event('change', { bubbles: true }));
  });
  render();
  return {
    get pending() { return pending; },
    clear() { latitude.value = longitude.value = accuracy.value = ''; showError(''); render(); },
    values() {
      if (!latitude.value && !longitude.value) return {};
      if (!render()) throw new Error('Introduce latitud entre −90 y 90 y longitud entre −180 y 180, ambas juntas.');
      return { latitude: Number(latitude.value), longitude: Number(longitude.value),
        ...(accuracy.value ? { accuracy_m: Number(accuracy.value) } : {}) };
    },
  };
}
