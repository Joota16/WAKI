/** Resumen visual del formulario; no persiste ni transmite información. */
export function initSummary() {
  const cards = document.querySelectorAll('.citizen-risk-card');
  const riskConfig = {
    critico: {
      badge: 'Nivel crítico',
      summary: 'Peligro Inminente',
    },
    'muy-alto': {
      badge: 'Nivel severo',
      summary: 'Nivel Muy Alto',
    },
    alto: {
      badge: 'Alerta amarilla',
      summary: 'Crecida / Nivel Alto',
    },
    normal: {
      badge: 'Tranquilo',
      summary: 'Normal / Sin Peligro',
    },
  };

  function updateRisk() {
    if (!document.querySelector('[name="nivelPeligro"]:checked')) {
      const badge = document.getElementById('badgeActiveRisk');
      badge.textContent = 'Selecciona una condición';
      delete badge.dataset.risk;
      const summary = document.getElementById('summaryRiesgoBadge');
      summary.textContent = 'Sin seleccionar';
      delete summary.dataset.risk;
    }
    cards.forEach(card => {
      const config = riskConfig[card.dataset.risk];
      const selected = card.querySelector('input').checked;
      card.classList.toggle('is-selected', selected);
      if (!selected) return;
      const badge = document.getElementById('badgeActiveRisk');
      badge.textContent = config.badge;
      badge.dataset.risk = card.dataset.risk;
      const summary = document.getElementById('summaryRiesgoBadge');
      summary.textContent = config.summary;
      summary.dataset.risk = card.dataset.risk;
    });
  }

  cards.forEach(card => card.querySelector('input').addEventListener('change', updateRisk));
  document.getElementById('citizenReportForm').addEventListener('reset', () => {
    queueMicrotask(() => { updateRisk(); updateClock(); });
  });
  updateRisk();
  updateClock();
}

export function localTime() {
  return new Intl.DateTimeFormat('es-PE', {
    timeZone: 'America/Lima', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(new Date());
}

export function updateClock() {
  document.getElementById('summaryHora').textContent = `${localTime()} (Lima)`;
}

