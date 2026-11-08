import { initOutboxView } from './outbox-view.js';
import { requestBackgroundSync } from '../offline/client.js';

/** Confirma primero la escritura local; solo el servidor confirma la recepción. */
export function initSubmission({ photos, location, modal }) {
  const form = document.getElementById('citizenReportForm');
  const fields = document.getElementById('reportFields');
  const error = document.getElementById('reportSubmitError');
  const status = document.getElementById('reportSubmitStatus');
  const editNotice = document.getElementById('reportEditingNotice');
  const submit = document.getElementById('btnSubmitCitizen');
  let saving = false, editing = null, currentId = null, revision = 0;
  const value = id => document.getElementById(id).value.trim();
  for (const event of ['input', 'change']) form.addEventListener(event, () => { revision += 1; });

  async function updateStatus() {
    if (!currentId) return;
    const item = await WakiOutbox.get(currentId);
    if (!item) return;
    status.hidden = false;
    status.textContent = item.state === 'sent' ? `Reporte enviado. Identificador: ${item.serverId}. Pendiente de verificación.`
      : item.state === 'error' ? `Guardado en este dispositivo. Requiere revisión: ${item.message}`
        : navigator.onLine !== false && item.state === 'sending' && item.leaseUntil > Date.now()
          ? 'Enviando reporte… Tus datos y fotos siguen guardados en este dispositivo.'
          : 'Guardado en este dispositivo. Pendiente de envío; se intentará enviar cuando haya conexión con WAKI.';
  }
  document.addEventListener('outbox-changed', () => updateStatus().catch(() => {}));
  initOutboxView({ onEdit: async id => {
    if (saving || photos.pending || location.pending) throw Error('Espera a que termine la operación actual.');
    if (photos.files().length || value('descripcionCiudadana')) {
      if (!window.confirm('¿Reemplazar el formulario actual con el reporte que quieres corregir?')) return;
    }
    const item = await WakiOutbox.get(id);
    if (item?.state !== 'error') throw Error('El reporte cambió. Actualiza los pendientes.');
    form.reset();
    await Promise.resolve(); // Deja finalizar los manejadores que limpian el formulario.
    const data = item.metadata;
    form.querySelectorAll('[name="nivelPeligro"]').forEach(input => { input.checked = input.value === data.observed_condition; });
    form.querySelectorAll('[name="situacion"]').forEach(input => { input.checked = data.situations.includes(input.value); });
    document.getElementById('descripcionCiudadana').value = data.observations;
    document.getElementById('report-phone').value = data.phone || '';
    document.getElementById('report-phone').dispatchEvent(new Event('input', { bubbles: true }));
    document.getElementById('situation-other-description').value = data.other_situation;
    location.restore(data);
    await photos.restore(item.files.map(file => new File([file.blob], file.name, { type: file.type })));
    editing = item; editNotice.hidden = false;
    form.dispatchEvent(new Event('change', { bubbles: true }));
    form.querySelector('[name="nivelPeligro"]:checked')?.dispatchEvent(new Event('change', { bubbles: true }));
    document.getElementById('situation-other').dispatchEvent(new Event('change', { bubbles: true }));
    form.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (saving) return;
    error.hidden = true;
    try {
      if (photos.pending || location.pending) throw Error('Espera a que termine la comprobación de fotos o la obtención de tu ubicación.');
      const selected = photos.files();
      if (!selected.length) throw Error('Adjunta al menos una fotografía del río.');
      if (!form.reportValidity()) return;
      const metadata = {
        client_created_at: editing?.createdAt || new Date().toISOString(),
        observations: value('descripcionCiudadana'), phone: value('report-phone') || null,
        observed_condition: form.querySelector('[name="nivelPeligro"]:checked').value,
        situations: [...form.querySelectorAll('[name="situacion"]:checked')].map(input => input.value),
        other_situation: document.getElementById('situation-other').checked ? value('situation-other-description') : '',
        ...location.values(),
      };
      saving = true; fields.disabled = true;
      submit.querySelector('[data-submit-label]').textContent = 'Guardando en este dispositivo…';
      let item;
      try {
        item = await WakiOutbox.enqueue(metadata, selected, Number(form.dataset.uploadTimeoutSeconds) * 1000, editing?.id);
      } catch (failure) {
        throw Error(failure.name === 'QuotaExceededError'
          ? 'No hay espacio para guardar las fotos. Libera espacio o reduce su tamaño. El reporte no se guardó; tus datos siguen en el formulario.'
          : 'No se pudo guardar el reporte en este dispositivo. Comprueba el almacenamiento del navegador. Tus datos siguen en el formulario.');
      }
      currentId = item.id; editing = null; editNotice.hidden = true;
      fields.disabled = false;
      form.reset(); photos.clear(); location.clear();
      await WakiReportSync.notify();
      await updateStatus();
      navigator.storage?.persist?.().catch(() => {});
      requestBackgroundSync();
      if (navigator.onLine !== false) {
        const submittedRevision = revision;
        WakiReportSync.run({ onlyId: item.id }).then(async () => {
          const saved = await WakiOutbox.get(item.id);
          if (saved?.state === 'sent' && currentId === item.id && revision === submittedRevision) {
            modal.show({ id: saved.serverId, created_at: saved.receivedAt });
          }
          requestBackgroundSync();
        }).catch(() => { updateStatus().catch(() => {}); });
      }
    } catch (failure) {
      error.textContent = failure.message; error.hidden = false; error.focus();
    } finally {
      saving = false; fields.disabled = false;
      submit.querySelector('[data-submit-label]').textContent = 'Enviar reporte';
    }
  });
}
