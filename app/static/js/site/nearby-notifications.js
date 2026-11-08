import { hasAlertZone } from './alert-zones.js';
import { workerReady } from '../offline/client.js';

const STORAGE = 'waki-nearby-notifications';
let settings = null;
try { settings = JSON.parse(localStorage.getItem(STORAGE) || 'null'); } catch { /* Configuración opcional. */ }
let maxAge = 86400;

export function isNearbyAlert(item) {
  if (!settings || Date.now() / 1000 - settings.locationAt >= maxAge || !hasAlertZone(item)) return false;
  const rad = value => value * Math.PI / 180;
  const a = Math.sin(rad(item.latitude - settings.latitude) / 2) ** 2
    + Math.cos(rad(settings.latitude)) * Math.cos(rad(item.latitude))
    * Math.sin(rad(item.longitude - settings.longitude) / 2) ** 2;
  return 6371000 * 2 * Math.asin(Math.sqrt(Math.min(1, a))) <= item.radius_m;
}

export function initNearbyNotifications() {
  const dialog = document.getElementById('nearby-notifications-dialog');
  if (!dialog) return;
  const status = document.getElementById('nearby-notifications-status');
  const locationButton = document.getElementById('nearby-location');
  const pushButton = document.getElementById('nearby-push');
  const disableButton = document.getElementById('nearby-disable');
  const supported = window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  let config = null, busy = false;
  const worker = supported ? workerReady : null;
  // El registro compartido funciona también sin soporte de notificaciones.
  worker?.catch(() => {});

  function save() {
    if (settings) localStorage.setItem(STORAGE, JSON.stringify(settings));
    else localStorage.removeItem(STORAGE);
    document.dispatchEvent(new Event('nearby-location-changed'));
  }
  function update() {
    locationButton.disabled = pushButton.disabled = disableButton.disabled = busy;
    locationButton.textContent = settings ? 'Actualizar mi ubicación' : 'Activar avisos cercanos';
    pushButton.disabled = busy || !supported || !settings || config?.enabled !== true || Notification.permission === 'denied';
    disableButton.hidden = !settings;
    document.getElementById('nearby-push-support').textContent = !supported
      ? 'Este navegador permite consultar los avisos dentro de WAKI. Para recibirlos con la aplicación cerrada, usa un navegador compatible; en iPhone, abre WAKI instalado en la pantalla de inicio.'
      : Notification.permission === 'denied' ? 'Las notificaciones están bloqueadas. Puedes habilitarlas desde los permisos del navegador.'
        : config?.enabled === false ? 'El servidor tiene desactivadas las notificaciones con WAKI cerrado.'
          : 'Puedes activar también las notificaciones con WAKI cerrado.';
    if (settings && !busy) {
      const expired = Date.now() / 1000 - settings.locationAt >= maxAge;
      status.textContent = expired ? 'Tu ubicación venció. Actualízala para volver a recibir avisos cercanos.'
        : `Ubicación compartida: ${new Date(settings.locationAt * 1000).toLocaleString('es-PE', { timeZone: 'America/Lima' })} (Lima). ${settings.push ? 'Notificaciones con WAKI cerrado activadas.' : 'Avisos cercanos mientras WAKI está abierto.'}`;
    }
  }
  function locate() {
    return new Promise((resolve, reject) => {
      if (!window.isSecureContext || !navigator.geolocation) return reject(Error('Tu navegador necesita HTTPS y acceso a ubicación.'));
      navigator.geolocation.getCurrentPosition(position => {
        if (position.coords.accuracy > 1000) return reject(Error('La ubicación es demasiado imprecisa. Activa la ubicación precisa y vuelve a intentar.'));
        resolve(position);
      }, () => reject(Error('No se pudo obtener tu ubicación. Revisa el permiso de ubicación y vuelve a intentar.')),
      { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 });
    });
  }
  async function api(method, body) {
    const response = await fetch('/api/notifications/subscription', { method, cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-WAKI-Client': 'browser' }, body: JSON.stringify(body) });
    if (!response.ok) {
      const error = await response.json().catch(() => null);
      throw Error(typeof error?.detail === 'string' ? error.detail : 'No se pudo guardar la configuración. Vuelve a intentar.');
    }
  }
  async function synchronizeSubscription() {
    if (!settings?.push || !supported) return;
    const registration = await worker;
    const subscription = await registration.pushManager.getSubscription();
    if (!subscription) { settings.push = false; save(); return; }
    await api('PUT', { token: settings.token, subscription: subscription.toJSON(),
      latitude: settings.latitude, longitude: settings.longitude, accuracy_m: settings.accuracy });
  }
  async function shareLocation(position) {
    settings = { ...settings, token: settings?.token || crypto.randomUUID(), latitude: position.coords.latitude,
      longitude: position.coords.longitude, accuracy: position.coords.accuracy, locationAt: Date.now() / 1000 };
    save();
    await synchronizeSubscription();
  }
  async function operation(action) {
    if (busy) return;
    busy = true; update(); status.textContent = 'Configurando avisos…';
    try { await action(); busy = false; update(); }
    catch (error) { busy = false; update(); status.textContent = error.message; }
  }
  locationButton.addEventListener('click', () => operation(async () => shareLocation(await locate())));
  pushButton.addEventListener('click', () => operation(async () => {
    // La solicitud se inicia directamente desde el toque del usuario.
    if (await Notification.requestPermission() !== 'granted') throw Error('No se activaron las notificaciones. Puedes seguir viendo los avisos dentro de WAKI.');
    await shareLocation(await locate());
    const registration = await worker;
    await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      const key = Uint8Array.from(atob(config.public_key.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
      subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
    }
    await api('PUT', { token: settings.token, subscription: subscription.toJSON(),
      latitude: settings.latitude, longitude: settings.longitude, accuracy_m: settings.accuracy });
    settings.push = true; save();
  }));
  disableButton.addEventListener('click', () => operation(async () => {
    if (settings?.token) await api('DELETE', { token: settings.token });
    if (supported) {
      const registration = await worker;
      await (await registration.pushManager.getSubscription())?.unsubscribe();
    }
    settings = null; save(); status.textContent = 'Avisos por cercanía desactivados. Puedes consultar todos los avisos desde la campana.';
  }));
  document.addEventListener('click', event => {
    if (!event.target.closest('[data-open-notification-settings]')) return;
    document.getElementById('important-notice-dialog')?.close();
    update(); dialog.showModal();
  });
  window.addEventListener('storage', event => {
    if (event.key !== STORAGE) return;
    try { settings = JSON.parse(event.newValue || 'null'); } catch { settings = null; }
    update(); document.dispatchEvent(new Event('nearby-location-changed'));
  });
  async function loadConfig() {
    try {
      const response = await fetch('/api/notifications/config', { cache: 'no-store' });
      if (!response.ok) throw Error();
      config = await response.json(); maxAge = config.location_max_age_seconds;
      document.getElementById('nearby-location-expiry').textContent = `${maxAge / 3600} horas`;
      update();
    } catch { status.textContent = 'No se pudo consultar la configuración de avisos. Recarga para volver a intentar.'; }
  }
  // Renueva la posición solo si ya se concedió permiso y la aplicación está visible.
  async function refreshLocation() {
    if (!settings || document.hidden || busy || !navigator.permissions) return;
    try {
      const permission = await navigator.permissions.query({ name: 'geolocation' });
      if (permission.state === 'granted') await shareLocation(await locate());
    } catch { /* La ubicación anterior vence; no se reutiliza indefinidamente. */ }
    update();
  }
  let timer = setInterval(refreshLocation, 300000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshLocation(); });
  window.addEventListener('pagehide', () => clearInterval(timer));
  window.addEventListener('pageshow', event => { if (event.persisted) { timer = setInterval(refreshLocation, 300000); refreshLocation(); } });
  loadConfig(); refreshLocation(); update();
}
