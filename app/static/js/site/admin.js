import { authenticatedJSON, getSession } from './auth.js';
import { element, message, requestJSON } from './utils.js';
import { alertKind } from './alerts.js';

export function initAdmin() {
  const page = document.querySelector('[data-admin-page]');
  if (!page) return;
  const tab = page.dataset.adminPage;
  const status = document.getElementById('admin-status');
  const filter = document.getElementById('admin-review-filter');
  const list = document.getElementById('admin-review-list');
  const notes = new Map();
  const levels = new Map();
  let offset = 0, singleId = document.getElementById('admin-reports-panel')?.dataset.reportId || null, sequence = 0, reviewing = false;
  const limit = 6;
  function isAdmin() { return getSession().user?.role === 'admin'; }
  async function loadAlerts() {
    if (tab !== 'alerts' || !isAdmin()) return;
    const container = document.getElementById('admin-active-alerts');
    try {
      const data = await requestJSON('/api/alerts');
      if (!isAdmin()) return;
      container.replaceChildren();
      for (const item of data.items) {
        const card = element('article', undefined, 'site-admin-alert');
        card.append(element('h3', `${alertKind(item.kind)} · ${item.title}`), element('p', item.location), element('p', item.message));
        const close = element('button', 'Finalizar aviso'); close.type = 'button';
        close.addEventListener('click', async () => {
          close.disabled = true;
          try { await authenticatedJSON(`/api/alerts/${item.id}/close`, { method: 'POST' }); status.textContent = 'Aviso finalizado.'; loadAlerts(); }
          catch (failure) { status.textContent = failure.message; close.disabled = false; }
        });
        card.append(close); container.append(card);
      }
      if (!data.items.length) container.textContent = 'No hay avisos activos.';
    } catch (failure) { container.textContent = failure.message; }
  }
  function reportCard(report) {
    const card = element('article', undefined, 'site-review-card');
    card.dataset.reviewId = report.id;
    card.append(element('h3', `Reporte ${report.id.slice(0, 8)}`),
      element('p', report.review_label, 'site-review-badge'), element('p', report.observations || 'Sin observaciones adicionales.'));
    if (report.photos.length) {
      const img = element('img'); img.src = report.photos[0].url; img.alt = 'Fotografía del reporte a revisar'; img.loading = 'lazy'; card.append(img);
    }
    const link = element('a', 'Ver reporte completo'); link.href = report.detail_url; link.target = '_blank'; link.rel = 'noopener noreferrer'; card.append(link);
    const levelLabel = element('label', 'Nivel de atención para Chillón · Tramo Comas');
    levelLabel.htmlFor = 'review-attention-' + report.id;
    const level = element('select'); level.id = levelLabel.htmlFor;
    for (const [value, text] of [['', 'Selecciona un nivel al validar'], ['monitoring', 'Seguimiento (verde)'],
      ['preventive', 'Atención preventiva (amarillo)'], ['priority', 'Atención prioritaria (rojo)']]) {
      const option = element('option', text); option.value = value; level.append(option);
    }
    level.value = levels.get(report.id) ?? report.attention_level ?? '';
    level.addEventListener('change', () => levels.set(report.id, level.value));
    card.append(levelLabel, level);
    const label = element('label', 'Justificación de la evaluación (obligatoria al validar; privada)');
    label.htmlFor = `review-notes-${report.id}`;
    const input = element('textarea'); input.id = label.htmlFor; input.maxLength = 1000; input.rows = 2;
    input.value = notes.get(report.id) ?? report.review_notes ?? '';
    input.addEventListener('input', () => notes.set(report.id, input.value));
    card.append(label, input);
    const actions = element('div', undefined, 'site-review-actions');
    for (const [decision, title] of [['validated', 'Validar'], ['discarded', 'Descartar'], ['pending', 'Volver a pendientes']]) {
      if (decision === report.review_status && decision !== 'validated') continue;
      const button = element('button', decision === 'validated' && report.review_status === 'validated' ? 'Actualizar evaluación' : title);
      button.type = 'button'; button.dataset.decision = decision;
      button.addEventListener('click', async () => {
        if (reviewing) return;
        if (decision === 'validated' && !level.value) {
          status.textContent = 'Selecciona el nivel de atención antes de validar el reporte.';
          level.focus(); return;
        }
        if (decision === 'validated' && !input.value.trim()) {
          status.textContent = 'Indica la justificación de la evaluación.';
          input.focus(); return;
        }
        reviewing = true; actions.querySelectorAll('button').forEach(node => { node.disabled = true; });
        input.disabled = true; level.disabled = true;
        try {
          const updated = await authenticatedJSON(`/api/reports/${report.id}/review`, {
            method: 'POST', body: JSON.stringify({ decision, notes: input.value, expected_version: report.review_version,
              attention_level: decision === 'validated' ? level.value : null }),
          });
          notes.delete(report.id); levels.delete(report.id); status.textContent = updated.review_label;
          document.dispatchEvent(new Event('reports-changed'));
        } catch (failure) { status.textContent = failure.message; }
        finally { reviewing = false; loadReports(); }
      });
      actions.append(button);
    }
    card.append(actions);
    return card;
  }
  async function loadReports() {
    if (tab !== 'reports' || !isAdmin() || reviewing) return;
    const current = ++sequence;
    list.textContent = 'Cargando reportes…';
    try {
      const url = singleId ? `/api/reports/${singleId}`
        : `/api/reports?review_status=${filter.value}&limit=${limit}&offset=${offset}`;
      const data = await authenticatedJSON(url);
      if (current !== sequence || !isAdmin()) return;
      const items = singleId ? [data] : data.items;
      const total = singleId ? 1 : data.total;
      if (singleId) filter.value = data.review_status;
      if (!singleId && offset && !items.length) { offset = 0; return loadReports(); }
      list.replaceChildren(...items.map(reportCard));
      if (!items.length) list.textContent = 'No hay reportes en este estado.';
      document.getElementById('admin-reports-page').textContent = total ? `${offset + 1}–${offset + items.length} de ${total}` : 'Sin reportes';
      document.getElementById('admin-reports-previous').disabled = !!singleId || offset === 0;
      document.getElementById('admin-reports-next').disabled = !!singleId || offset + limit >= total;
    } catch (failure) { if (current === sequence) list.textContent = failure.message; }
  }
  filter?.addEventListener('change', () => { offset = 0; singleId = null; loadReports(); });
  document.getElementById('admin-refresh-reports')?.addEventListener('click', () => loadReports());
  document.getElementById('admin-reports-previous')?.addEventListener('click', () => { offset = Math.max(0, offset - limit); loadReports(); });
  document.getElementById('admin-reports-next')?.addEventListener('click', () => { offset += limit; loadReports(); });
  document.addEventListener('reports-changed', () => {
    if (list?.contains(document.activeElement) && document.activeElement.matches('textarea, select')) return;
    loadReports();
  });
  document.addEventListener('alerts-changed', () => { if (tab === 'alerts') loadAlerts(); });
  const form = document.getElementById('admin-alert-form');
  form?.addEventListener('submit', async event => {
    event.preventDefault();
    const button = document.getElementById('admin-publish-alert');
    if (button.disabled || !isAdmin()) return;
    button.disabled = true; status.textContent = 'Publicando aviso…';
    try {
      await authenticatedJSON('/api/alerts', { method: 'POST', body: JSON.stringify({
        kind: document.getElementById('admin-alert-kind').value, title: document.getElementById('admin-alert-title').value,
        location: document.getElementById('admin-alert-location').value, message: document.getElementById('admin-alert-message').value,
      }) });
      form.reset(); status.textContent = 'Aviso publicado.'; loadAlerts(); message('Aviso publicado para quienes tienen WAKI abierto.');
    } catch (failure) { status.textContent = failure.message; }
    finally { button.disabled = false; }
  });
  let hadAdminSession = isAdmin();
  document.addEventListener('session-changed', () => {
    if (!isAdmin()) {
      ++sequence; notes.clear(); levels.clear();
      list?.replaceChildren();
      form?.reset();
      document.getElementById('admin-active-alerts')?.replaceChildren();
    } else if (!hadAdminSession) {
      if (tab === 'alerts') loadAlerts(); else loadReports();
    }
    hadAdminSession = isAdmin();
  });
  if (tab === 'alerts') loadAlerts(); else loadReports();
}
