/** Envía datos y archivos al servidor y conserva el borrador si ocurre un error. */
export function initSubmission({ photos, location, modal }) {
  const form = document.getElementById('citizenReportForm');
  const fields = document.getElementById('reportFields');
  const error = document.getElementById('reportSubmitError');
  const submit = document.getElementById('btnSubmitCitizen');
  function requestKey() {
    if (crypto.randomUUID) return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map(byte => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  let key = requestKey();
  let submitting = false;
  const value = id => document.getElementById(id).value.trim();
  for (const event of ['input', 'change']) {
    form.addEventListener(event, () => { if (!submitting) key = requestKey(); });
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting) return;
    error.hidden = true;
    try {
      if (photos.pending || location.pending) throw new Error('Espera a que termine la comprobación de fotos o la obtención de tu ubicación.');
      const selected = photos.files();
      if (!selected.length) throw new Error('Adjunta al menos una fotografía del río.');
      if (!form.reportValidity()) return;
      const metadata = {
        observations: value('descripcionCiudadana'),
        observed_condition: form.querySelector('[name="nivelPeligro"]:checked').value,
        situations: [...form.querySelectorAll('[name="situacion"]:checked')].map(input => input.value),
        other_situation: document.getElementById('situation-other').checked ? value('situation-other-description') : '',
        ...location.values(),
      };
      const data = new FormData();
      data.append('metadata', JSON.stringify(metadata));
      selected.forEach(file => data.append('files', file, file.name));
      submitting = true; fields.disabled = true;
      submit.querySelector('[data-submit-label]').textContent = 'Guardando reporte…';
      let response;
      try {
        response = await fetch('/api/reports', { method: 'POST', headers: { 'Idempotency-Key': key }, body: data });
      } catch {
        throw new Error('No se pudo confirmar el envío. Revisa tu conexión y vuelve a intentarlo; conservamos tus datos y fotos.');
      }
      const result = await response.json().catch(() => null);
      if (!response.ok) {
        if (typeof result?.detail === 'string') throw new Error(result.detail);
        if (response.status === 422) throw new Error('Revisa los campos y las fotografías. Algún dato no cumple los límites del formulario.');
        throw new Error('El servidor no pudo guardar el reporte. Tus datos siguen aquí para reintentar.');
      }
      if (!result?.id || !result?.detail_url) throw new Error('No se pudo confirmar el registro. Vuelve a intentarlo.');
      fields.disabled = false;
      form.reset(); photos.clear(); location.clear(); key = requestKey();
      modal.show(result);
    } catch (failure) {
      error.textContent = failure.message; error.hidden = false; error.focus();
    } finally {
      submitting = false; fields.disabled = false;
      submit.querySelector('[data-submit-label]').textContent = 'Enviar reporte';
    }
  });
}
