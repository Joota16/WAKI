// Solo se guardan recursos públicos y el formulario anónimo; nunca cuentas ni APIs.
importScripts('/static/js/offline/outbox.js', '/static/js/offline/sync.js');
const FORM_CACHE = 'waki-report-form-__WAKI_OFFLINE_VERSION__';

self.addEventListener('install', event => event.waitUntil((async () => {
  const response = await fetch('/pwa-assets.json', { cache: 'no-store', credentials: 'omit' });
  if (!response.ok) throw Error('No se pudo preparar el formulario sin conexión.');
  const { assets } = await response.json();
  const cache = await caches.open(FORM_CACHE);
  await cache.addAll([...assets, '/reportar'].map(url => new Request(url, { cache: 'reload', credentials: 'omit' })));
  await self.skipWaiting();
})()));

self.addEventListener('activate', event => event.waitUntil((async () => {
  const names = await caches.keys();
  await Promise.all(names.filter(name => name.startsWith('waki-report-form-') && name !== FORM_CACHE).map(name => caches.delete(name)));
  await self.clients.claim();
})()));

self.addEventListener('fetch', event => {
  const request = event.request, url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (request.mode === 'navigate' && url.pathname === '/reportar') {
    event.respondWith((async () => {
      const cache = await caches.open(FORM_CACHE);
      // Abre inmediatamente el formulario ya preparado, incluso con una red lenta.
      const stored = await cache.match('/reportar');
      if (stored) return stored;
      return fetch(request);
    })());
  } else if (url.pathname.startsWith('/static/')) {
    event.respondWith((async () => {
      const stored = await (await caches.open(FORM_CACHE)).match(request);
      return stored || fetch(request);
    })());
  } else if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(async () => {
      const page = await (await caches.open(FORM_CACHE)).match('/static/offline.html');
      return page || Response.error();
    }));
  }
});

self.addEventListener('sync', event => {
  if (event.tag !== 'waki-send-reports') return;
  event.waitUntil((async () => {
    await WakiReportSync.run();
    if ((await WakiOutbox.list()).some(item => ['pending', 'sending'].includes(item.state))) {
      // El navegador decide cuándo volver a despertar el worker.
      throw Error('Quedan reportes pendientes de confirmar.');
    }
  })());
});

self.addEventListener('push', event => {
  event.waitUntil((async () => {
    let notice;
    try { notice = event.data.json(); } catch { return; }
    if (!/^[a-f0-9-]{36}$/.test(notice.id)) return;
    // Evita mostrar un aviso que fue finalizado mientras estaba en tránsito.
    try {
      const response = await fetch('/api/alerts', { cache: 'no-store', signal: AbortSignal.timeout(5000) });
      if (response.ok && !(await response.json()).items.some(item => item.id === notice.id && item.active)) return;
    } catch { /* El mensaje tiene una vigencia corta en el servicio de entrega. */ }
    await self.registration.showNotification(notice.title || 'Aviso cercano de WAKI', {
      body: notice.body, icon: '/static/img/icons/waki-192.png', badge: '/static/img/icons/waki-192.png',
      tag: `waki-alert-${notice.id}`, data: { url: `/?aviso=${encodeURIComponent(notice.id)}` },
    });
  })());
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil((async () => {
    const destination = new URL(event.notification.data?.url || '/', self.location.origin);
    if (destination.origin !== self.location.origin) return;
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    const existing = windows.find(client => new URL(client.url).origin === self.location.origin);
    if (existing) { await existing.navigate(destination.href); await existing.focus(); }
    else await self.clients.openWindow(destination.href);
  })());
});
