export function renderRiver(key, data) {
  // Highlight row in table
  document.querySelectorAll('.river-row').forEach(row => {
    row.classList.remove('bg-sky-50/60', 'bg-sky-50/30');
  });
  const rowEl = document.getElementById(`row-${key}`);
  if (rowEl) rowEl.classList.add('bg-sky-50/60');

  // Update Detail Card Headers
  document.getElementById('card-river-title').textContent = data.title;
  document.getElementById('card-river-station').textContent = data.station;
  document.getElementById('card-river-badge-text').textContent = data.badgeText;
  document.getElementById('card-river-badge').className = `inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold ${data.badgeClass} shadow-sm shrink-0`;


}

export function switchTab(tabKey) {
  const tabs = ['resumen', 'imagenes', 'reportes'];
  if (!tabs.includes(tabKey)) return;
  tabs.forEach(t => {
    const panel = document.getElementById(`tab-panel-${t}`);
    const btn = document.getElementById(`tab-btn-${t}`);
    if (panel && btn) {
      if (t === tabKey) {
        panel.classList.remove('hidden');
        btn.className = 'tab-button py-2 border-b-2 border-sky-600 text-sky-600 font-semibold whitespace-nowrap transition-colors';
      } else {
        panel.classList.add('hidden');
        btn.className = 'tab-button py-2 border-b-2 border-transparent hover:text-slate-900 text-slate-500 whitespace-nowrap transition-colors';
      }
    }
  });
}
