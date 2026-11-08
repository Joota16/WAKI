import './outbox.js';
import './sync.js';

// El registro no depende de PushManager ni solicita permisos de notificación.
export const workerReady = globalThis.isSecureContext && 'serviceWorker' in navigator
  ? navigator.serviceWorker.register('/service-worker.js', { scope: '/', updateViaCache: 'none' }).catch(() => null)
  : Promise.resolve(null);

export async function requestBackgroundSync() {
  const registration = await workerReady;
  if (!registration?.active || !('sync' in registration)) return;
  try { await registration.sync.register('waki-send-reports'); } catch { /* Se reintenta al abrir WAKI. */ }
}

let initialized = false;
export function initOfflineReports() {
  if (initialized) return;
  initialized = true;
  const channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('waki-report-outbox') : null;
  channel?.addEventListener('message', () => document.dispatchEvent(new Event('outbox-changed')));
  navigator.serviceWorker?.addEventListener('message', event => {
    if (event.data?.type === 'outbox-changed') document.dispatchEvent(new Event('outbox-changed'));
  });
  const kick = (force = false) => {
    if (document.hidden || navigator.onLine === false) return;
    WakiReportSync.run({ force }).then(async () => {
      if ((await WakiOutbox.list()).some(row => ['pending', 'sending'].includes(row.state))) requestBackgroundSync();
    }).catch(() => {});
  };
  window.addEventListener('online', () => kick(true));
  window.addEventListener('pageshow', () => kick());
  document.addEventListener('visibilitychange', () => kick());
  navigator.serviceWorker?.addEventListener('controllerchange', () => {
    WakiOutbox.list().then(rows => {
      if (rows.some(row => ['pending', 'sending'].includes(row.state))) requestBackgroundSync();
    }).catch(() => {});
    kick();
  });
  let timer = setInterval(() => kick(), 15000);
  window.addEventListener('pagehide', () => clearInterval(timer));
  window.addEventListener('pageshow', event => { if (event.persisted) timer = setInterval(() => kick(), 15000); });
  workerReady.then(registration => {
    registration?.addEventListener('updatefound', () => {
      registration.installing?.addEventListener('statechange', () => document.dispatchEvent(new Event('offline-ready-changed')));
    });
    document.dispatchEvent(new Event('offline-ready-changed'));
    kick();
  });
  kick();
}
