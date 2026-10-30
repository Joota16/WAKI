import { ATTENTION_STYLES, attentionStyle, RIVERS_DATA } from './data.js';
import { renderRiver } from './view.js';
import { requestJSON } from '../site/utils.js';

const formatDate = new Intl.DateTimeFormat('es-PE', {
  timeZone: 'America/Lima', dateStyle: 'short', timeStyle: 'short',
});

export function initAttention(riverMap) {
  const status = document.getElementById('attention-status');
  const retry = document.getElementById('retry-attention');
  let loading = false, pending = false, stopped = false;

  function render(state, unavailable = false) {
    const river = RIVERS_DATA.chillon;
    river.attentionLevel = state.level;
    river.attentionLabel = state.label;
    renderRiver('chillon', river);
    const badge = document.getElementById('river-attention-chillon');
    badge.textContent = state.label;
    badge.className = 'inline-flex px-2.5 py-1 rounded-lg border text-xs font-semibold ' + attentionStyle(state.level).badgeClass;
    document.getElementById('row-chillon').dataset.attentionLevel = state.level || 'pending';
    const evaluated = document.getElementById('river-evaluated-chillon');
    evaluated.textContent = state.evaluated_at ? formatDate.format(new Date(state.evaluated_at)) + ' (Lima)'
      : unavailable ? 'Sin datos' : 'Sin evaluación';
    const source = document.getElementById('attention-source');
    source.hidden = !state.source_report_url;
    if (state.source_report_url) source.href = state.source_report_url; else source.removeAttribute('href');
    riverMap?.updateAttention('chillon');
  }

  async function refresh() {
    if (stopped) return;
    if (loading) { pending = true; return; }
    loading = true;
    try {
      const state = await requestJSON('/api/attention/chillon');
      if (stopped) return;
      if (state.river_id !== 'chillon' || (state.level !== null && !ATTENTION_STYLES[state.level])
        || typeof state.label !== 'string'
        || (state.level !== null && (!state.evaluated_at || !Number.isFinite(Date.parse(state.evaluated_at))
          || state.source_report_url !== '/reportes/' + state.source_report_id))) throw new Error('Evaluación inválida.');
      render(state);
      status.hidden = true; retry.hidden = true;
    } catch {
      if (stopped) return;
      render({ level: null, label: 'Evaluación no disponible' }, true);
      status.textContent = 'No se pudo consultar el nivel de atención.';
      status.hidden = false; retry.hidden = false;
    } finally {
      loading = false;
      if (pending) { pending = false; refresh(); }
    }
  }
  retry.addEventListener('click', refresh);
  document.addEventListener('reports-changed', refresh);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  const poll = () => { if (!document.hidden) refresh(); };
  let timer = setInterval(poll, 15000);
  window.addEventListener('pagehide', () => { stopped = true; clearInterval(timer); });
  window.addEventListener('pageshow', event => {
    if (event.persisted) { stopped = false; timer = setInterval(poll, 15000); refresh(); }
  });
  refresh();
}
