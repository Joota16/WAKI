/** Controles compartidos por el informe independiente y su ventana emergente. */
export function initAnalysisViewer(panel, { onStatusChange } = {}) {
  const events = new AbortController();
  const image = panel.querySelector('#analysis-preview');
  const imageError = panel.querySelector('#analysis-image-error');
  const buttons = panel.querySelectorAll('[data-analysis-preview]');
  buttons.forEach(button => {
    button.addEventListener('click', () => {
      imageError.hidden = true;
      image.hidden = false;
      image.alt = button.dataset.label;
      panel.querySelector('#analysis-preview-label').textContent = button.dataset.label;
      image.src = button.dataset.analysisPreview;
      buttons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    }, { signal: events.signal });
  });
  image.addEventListener('error', () => { image.hidden = true; imageError.hidden = false; }, { signal: events.signal });
  image.addEventListener('load', () => { image.hidden = false; imageError.hidden = true; }, { signal: events.signal });
  // La primera carga puede haber terminado antes de inicializar el controlador.
  if (image.complete && !image.naturalWidth) { image.hidden = true; imageError.hidden = false; }
  let timer, controller, stopped = false;
  async function refresh() {
    const active = new AbortController();
    controller = active;
    const timeout = setTimeout(() => active.abort(), 10000);
    try {
      const response = await fetch(`/api/analyses/${panel.dataset.id}`, { signal: active.signal, cache: 'no-store' });
      if (!response.ok) throw new Error('No disponible');
      const item = await response.json();
      if (stopped) return;
      if (item.status !== panel.dataset.status) {
        onStatusChange?.();
        return;
      }
      panel.querySelector('#analysis-live-status').textContent = item.message || item.status_label;
    } catch {
      if (!stopped) panel.querySelector('#analysis-live-status').textContent = 'No se pudo actualizar el estado. Reintentaremos en unos segundos.';
    } finally {
      clearTimeout(timeout);
      if (!stopped) timer = setTimeout(refresh, 5000);
    }
  }
  if (['queued', 'processing'].includes(panel.dataset.status)) timer = setTimeout(refresh, 5000);
  return {
    destroy() { stopped = true; events.abort(); controller?.abort(); clearTimeout(timer); },
  };
}
