/** Actualiza las vistas públicas cuando cambia la revisión o la sesión. */
export function initPublicReports(renderAccount) {
  let generation = 0, controller;
  async function refresh() {
    const listing = document.getElementById('public-reports');
    const detail = document.querySelector('[data-report-detail-id]');
    const currentView = listing || detail;
    if (!currentView) return;
    const current = ++generation;
    controller?.abort();
    const active = new AbortController(); controller = active;
    const timeout = setTimeout(() => active.abort(), 15000);
    currentView.setAttribute('aria-busy', 'true');
    currentView.replaceChildren(document.createTextNode('Actualizando reporte…'));
    try {
      const response = await fetch(detail ? `/reportes/${detail.dataset.reportDetailId}` : location.href,
        { cache: 'no-store', signal: active.signal });
      if (current !== generation) return;
      if (response.status === 404 && detail) {
        const title = document.createElement('h1'); title.textContent = 'Este reporte ya no está disponible.';
        const link = document.createElement('a'); link.href = '/reportes'; link.textContent = 'Ver reportes disponibles';
        currentView.replaceChildren(title, link); currentView.removeAttribute('aria-busy');
        return;
      }
      if (!response.ok) throw new Error('No disponible');
      const html = await response.text();
      if (current !== generation) return;
      const updated = new DOMParser().parseFromString(html, 'text/html').getElementById(currentView.id);
      if (!updated) throw new Error('Respuesta inválida');
      currentView.replaceWith(updated); renderAccount();
      if (listing && response.redirected) history.replaceState(null, '', response.url);
    } catch {
      if (current === generation) {
        currentView.textContent = 'No se pudo actualizar el reporte. Recarga la página para consultar su estado.';
        currentView.removeAttribute('aria-busy');
      }
    } finally { clearTimeout(timeout); }
  }
  document.addEventListener('reports-changed', refresh);
  document.addEventListener('session-changed', refresh);
}
