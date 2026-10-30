const timestamp = new Intl.DateTimeFormat('es-PE', {
  timeZone: 'America/Lima', day: '2-digit', month: '2-digit', year: 'numeric',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
});

/** La cámara muestra fotos recibidas, con una fecha vinculada a cada archivo. */
export function initCamera() {
  const element = id => document.getElementById(id);
  const panel = element('camera-panel');
  const cameras = JSON.parse(panel.dataset.cameras);
  const image = element('camera-image');
  const dialog = element('camera-dialog');
  const fullscreen = element('camera-fullscreen');
  let cameraId = null, frame = null, controller = null, timer = null, sequence = 0;
  let clockOffset = 0, pollSeconds = 5, staleAfter = 120;

  function updateAge() {
    if (!frame) return;
    const seconds = Math.max(0, Math.floor((Date.now() + clockOffset - Date.parse(frame.received_at)) / 1000));
    const age = seconds < 60 ? `${seconds} s` : seconds < 3600 ? `${Math.floor(seconds / 60)} min`
      : seconds < 86400 ? `${Math.floor(seconds / 3600)} h` : `${Math.floor(seconds / 86400)} días`;
    element('camera-age').textContent = `Recibida hace ${age}`;
    element('camera-badge').textContent = seconds <= staleAfter ? 'Captura recibida recientemente' : 'Última captura guardada';
    element('camera-badge').classList.toggle('camera-recent', seconds <= staleAfter);
  }

  function clear() {
    frame = null;
    image.hidden = true; image.removeAttribute('src');
    element('camera-empty').hidden = false;
    element('camera-badge').textContent = 'Sin imágenes';
    element('camera-badge').classList.remove('camera-recent');
    element('camera-timestamp').textContent = 'Sin capturas recibidas';
    element('camera-timestamp').removeAttribute('datetime');
    element('camera-timestamp').removeAttribute('title');
    element('camera-age').textContent = '';
    element('camera-status').textContent = 'Consultando capturas…';
    fullscreen.disabled = true;
    element('camera-dialog-image').removeAttribute('src');
    if (dialog.open) dialog.close();
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (!document.hidden && !panel.closest('.tab-panel').classList.contains('hidden')) refresh();
      else schedule();
    }, pollSeconds * 1000);
  }

  async function refresh() {
    clearTimeout(timer);
    controller?.abort();
    const request = new AbortController(); controller = request;
    const current = ++sequence;
    const timeout = setTimeout(() => request.abort(), 10000);
    try {
      const response = await fetch(`/api/cameras/${cameraId}/latest`, { signal: request.signal, cache: 'no-store' });
      if (!response.ok) throw new Error('Consulta de cámara no disponible');
      const data = await response.json();
      if (current !== sequence) return;
      if (data.camera.id !== cameraId) throw new Error('Cámara inesperada');
      clockOffset = Date.parse(data.server_time) - Date.now();
      pollSeconds = data.poll_seconds;
      staleAfter = data.stale_after_seconds;
      element('camera-name').textContent = data.camera.name;
      if (!data.latest) {
        clear();
        element('camera-status').textContent = 'Todavía no se han recibido fotografías de esta cámara.';
        return;
      }
      if (frame?.id !== data.latest.id) {
        // Se carga primero para conservar la foto anterior si falla la nueva.
        const nextImage = new Image();
        await new Promise((resolve, reject) => {
          const cleanup = () => {
            request.signal.removeEventListener('abort', abort);
            nextImage.onload = nextImage.onerror = null;
          };
          const abort = () => { cleanup(); nextImage.src = ''; reject(new Error('Carga cancelada')); };
          nextImage.onload = () => { cleanup(); resolve(); };
          nextImage.onerror = () => { cleanup(); reject(new Error('Imagen no disponible')); };
          request.signal.addEventListener('abort', abort, { once: true });
          if (request.signal.aborted) abort();
          else nextImage.src = data.latest.image_url;
        });
        if (current !== sequence) return;
        frame = data.latest;
        image.src = nextImage.src;
        image.hidden = false; element('camera-empty').hidden = true;
        fullscreen.disabled = false;
        const date = frame.captured_at || frame.received_at;
        const label = `${frame.captured_at ? 'Capturada' : 'Recibida'}: ${timestamp.format(new Date(date))} (Lima)`;
        element('camera-timestamp').textContent = label;
        element('camera-timestamp').setAttribute('datetime', date);
        element('camera-timestamp').title = `Recepción: ${timestamp.format(new Date(frame.received_at))} (Lima)`;
        element('camera-dialog-image').src = image.src;
        element('camera-dialog-caption').textContent = `${data.camera.name} · ${label}`;
      }
      element('camera-status').textContent = 'Última fotografía recibida. Actualización automática.';
      updateAge();
    } catch {
      if (current !== sequence) return;
      element('camera-status').textContent = 'No se pudo cargar la última captura. Puedes volver a actualizar; la fotografía visible conserva su fecha.';
    } finally {
      clearTimeout(timeout);
      if (current === sequence) schedule();
    }
  }

  element('camera-refresh').addEventListener('click', refresh);
  fullscreen.addEventListener('click', async () => {
    if (!frame) return;
    if (document.fullscreenElement === panel) { await document.exitFullscreen(); return; }
    if (panel.requestFullscreen && document.fullscreenEnabled) {
      try { await panel.requestFullscreen(); return; } catch { /* Vista ampliada compatible. */ }
    }
    if (!dialog.open) dialog.showModal();
  });
  document.addEventListener('fullscreenchange', () => {
    fullscreen.textContent = document.fullscreenElement === panel ? 'Salir de pantalla completa' : 'Pantalla completa';
  });
  element('camera-dialog-close').addEventListener('click', () => dialog.close());
  document.addEventListener('visibilitychange', () => { if (!document.hidden && cameraId) refresh(); });
  setInterval(updateAge, 1000);
  return {
    selectRiver(key) {
      if (cameraId === cameras[key]) return;
      controller?.abort(); clearTimeout(timer); sequence++;
      cameraId = cameras[key];
      clear();
      element('camera-name').textContent = 'Cámara del río Chillón';
      refresh();
    },
  };
}
