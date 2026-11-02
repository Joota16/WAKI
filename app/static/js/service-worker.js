// Solo notificaciones. Sin caché de páginas, respuestas ni funcionamiento sin internet.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));

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
