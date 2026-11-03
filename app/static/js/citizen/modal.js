import { updateClock } from './summary.js';

/** Muestra únicamente reportes que el servidor confirmó como guardados. */
export function initReportModal() {
  const modal = document.getElementById('successCitizenModal');
  const content = document.getElementById('successCitizenModalContent');
  const close = document.getElementById('btnReportAnother');
  let previousFocus;

  function hide() {
    content.classList.add('scale-95', 'opacity-0');
    content.classList.remove('scale-100', 'opacity-100');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    previousFocus?.focus();
    updateClock();
  }

  function show(report) {
    previousFocus = document.activeElement;
    document.getElementById('modalTicket').textContent = report.id;
    document.getElementById('modalHora').textContent = new Intl.DateTimeFormat('es-PE', {
      timeZone: 'America/Lima', dateStyle: 'short', timeStyle: 'medium',
    }).format(new Date(report.created_at));
    document.getElementById('viewSavedReport').href = '/reportes';
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    close.focus();
    requestAnimationFrame(() => {
      content.classList.remove('scale-95', 'opacity-0');
      content.classList.add('scale-100', 'opacity-100');
    });
  }
  close.addEventListener('click', hide);
  modal.addEventListener('click', event => {
    if (event.target === modal) hide();
  });
  document.addEventListener('keydown', event => {
    if (modal.classList.contains('hidden')) return;
    if (event.key === 'Escape') hide();
    if (event.key === 'Tab') {
      const targets = [...modal.querySelectorAll('a[href], button')];
      const first = targets[0];
      const last = targets.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });
  return { show };
}

