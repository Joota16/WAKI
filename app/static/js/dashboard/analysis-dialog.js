import { initAnalysisViewer } from '../analyses/viewer.js';

export function initAnalysisDialog() {
  const dialog = document.getElementById('analysis-report-dialog');
  const content = document.getElementById('analysis-dialog-content');
  const status = document.getElementById('analysis-dialog-status');
  const retry = document.getElementById('analysis-dialog-retry');
  const close = document.getElementById('analysis-dialog-close');
  let analysisId, trigger, controller, viewer, sequence = 0;

  async function load() {
    const current = ++sequence;
    controller?.abort();
    viewer?.destroy();
    viewer = null;
    content.replaceChildren();
    content.hidden = true;
    status.hidden = false;
    status.textContent = 'Cargando informe…';
    retry.hidden = true;
    const active = new AbortController();
    controller = active;
    const timeout = setTimeout(() => active.abort(), 10000);
    try {
      const response = await fetch(`/informes-ia/${encodeURIComponent(analysisId)}/contenido`,
        { signal: active.signal, cache: 'no-store' });
      if (!response.ok) throw new Error(response.status === 404 ? 'not_found' : 'request_failed');
      const html = await response.text();
      if (current !== sequence || !dialog.open) return;
      // Fragmento de la plantilla del servidor: Jinja escapa todos los campos dinámicos.
      const document = new DOMParser().parseFromString(html, 'text/html');
      const report = document.getElementById('analysis-detail');
      if (!report || report.dataset.id !== analysisId) throw new Error('invalid_report');
      content.replaceChildren(report);
      content.hidden = false;
      status.hidden = true;
      viewer = initAnalysisViewer(report, { onStatusChange: load });
    } catch (error) {
      if (current !== sequence || !dialog.open) return;
      status.textContent = error.message === 'not_found'
        ? 'Este informe ya no está disponible o venció su retención.'
        : 'No se pudo cargar el informe. Puedes reintentar sin salir del tablero.';
      retry.hidden = false;
    } finally {
      clearTimeout(timeout);
    }
  }

  function cleanup() {
    ++sequence;
    controller?.abort();
    viewer?.destroy();
    viewer = null;
    content.replaceChildren();
    document.documentElement.classList.remove('analysis-dialog-open');
    (trigger?.isConnected ? trigger : document.getElementById('tab-btn-imagenes'))?.focus({ preventScroll: true });
  }
  close.addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', cleanup);
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
  retry.addEventListener('click', load);
  window.addEventListener('pagehide', () => { if (dialog.open) dialog.close(); });
  return {
    open(id, button) {
      analysisId = id;
      trigger = button;
      if (!dialog.open) dialog.showModal();
      document.documentElement.classList.add('analysis-dialog-open');
      close.focus({ preventScroll: true });
      load();
    },
  };
}
