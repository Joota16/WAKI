// Catálogo del tablero. La evaluación se consulta en la API.
export const ATTENTION_STYLES = {
  pending: { color: '#64748b', badgeClass: 'bg-slate-100 text-slate-600 border-slate-300', markerClass: 'bg-slate-500' },
  monitoring: { color: '#10b981', badgeClass: 'bg-emerald-50 text-emerald-800 border-emerald-300', markerClass: 'bg-emerald-500' },
  preventive: { color: '#eab308', badgeClass: 'bg-yellow-50 text-yellow-800 border-yellow-300', markerClass: 'bg-yellow-500' },
  priority: { color: '#ef4444', badgeClass: 'bg-red-50 text-red-700 border-red-300', markerClass: 'bg-red-500' },
};
export const attentionStyle = level => ATTENTION_STYLES[level || 'pending'] || ATTENTION_STYLES.pending;

export const RIVERS_DATA = {
  chillon: {
    name: 'Río Chillón',
    stretch: 'Tramo Comas',
    title: 'Río Chillón – Tramo Comas',
    location: 'Lima',
    attentionLevel: null,
    attentionLabel: 'Pendiente de evaluación',
    zoom: 12.5,
  }
};
