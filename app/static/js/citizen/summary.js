/** Resumen visual del formulario; no persiste ni transmite información. */
export function initSummary() {
  const river = document.getElementById('cuencaSelect');
  const district = document.getElementById('distritoInput');
  const cards = document.querySelectorAll('.citizen-risk-card');
  const riskConfig = {
    critico: {
      badge: '🔴 Peligro Inminente Seleccionado',
      badgeClass: 'bg-error-container text-on-error-container',
      summary: '🚨 Peligro Inminente', border: 'border-error bg-error-container/20',
    },
    'muy-alto': {
      badge: '🟠 Nivel Muy Alto Seleccionado',
      badgeClass: 'bg-secondary-fixed text-on-secondary-container',
      summary: '⚠️ Nivel Muy Alto', border: 'border-secondary bg-secondary-fixed/20',
    },
    alto: {
      badge: '🟡 Nivel Alto Seleccionado',
      badgeClass: 'bg-tertiary-fixed text-on-tertiary-fixed-variant',
      summary: '🌊 Crecida / Nivel Alto', border: 'border-tertiary bg-tertiary-fixed/20',
    },
    normal: {
      badge: '🟢 Nivel Normal Seleccionado',
      badgeClass: 'bg-primary-fixed text-on-primary-fixed-variant',
      summary: '✅ Normal / Sin Peligro', border: 'border-primary bg-primary-fixed/20',
    },
  };

  function updateZone() {
    const suffix = district.value ? ` (${district.value})` : '';
    document.getElementById('summaryCuenca').textContent = `${river.value || 'Selecciona el río'}${suffix}`;
  }

  function updateRisk() {
    if (!document.querySelector('[name="nivelPeligro"]:checked')) {
      const badge = document.getElementById('badgeActiveRisk');
      badge.textContent = 'Selecciona una condición';
      badge.className = 'px-3 py-1 rounded-full text-xs font-bold bg-surface-container text-on-surface';
      const summary = document.getElementById('summaryRiesgoBadge');
      summary.textContent = 'Sin seleccionar';
      summary.className = 'px-2 py-0.5 rounded-full text-xs bg-surface-container text-on-surface';
    }
    cards.forEach(card => {
      const config = riskConfig[card.dataset.risk];
      const selected = card.querySelector('input').checked;
      card.classList.remove('border-error', 'border-secondary', 'border-tertiary', 'border-primary',
        'bg-error-container/20', 'bg-secondary-fixed/20', 'bg-tertiary-fixed/20', 'bg-primary-fixed/20');
      card.classList.add('border-transparent', 'bg-surface-container-low', 'opacity-85');
      if (!selected) return;
      card.classList.remove('border-transparent', 'bg-surface-container-low', 'opacity-85');
      card.classList.add(...config.border.split(' '));
      const badge = document.getElementById('badgeActiveRisk');
      badge.textContent = config.badge;
      badge.className = `px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide ${config.badgeClass}`;
      const summary = document.getElementById('summaryRiesgoBadge');
      summary.textContent = config.summary;
      summary.className = `px-2 py-0.5 rounded-full text-[11px] font-bold ${config.badgeClass}`;
    });
  }

  river.addEventListener('change', updateZone);
  district.addEventListener('input', updateZone);
  cards.forEach(card => card.querySelector('input').addEventListener('change', updateRisk));
  document.getElementById('citizenReportForm').addEventListener('reset', () => {
    queueMicrotask(() => { updateZone(); updateRisk(); updateClock(); });
  });
  updateZone();
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

