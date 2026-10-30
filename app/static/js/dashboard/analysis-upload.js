export function initAnalysisUpload({ onCreated }) {
  const form = document.getElementById('analysis-test-form');
  const input = document.getElementById('analysis-test-file');
  const key = document.getElementById('analysis-test-key');
  const preview = document.getElementById('analysis-test-preview');
  const status = document.getElementById('analysis-test-status');
  const submit = document.getElementById('analysis-test-submit');
  const limitMB = Number(form.dataset.limitMb);
  let river = 'chillon', busy = false, controller, objectURL, stopped = false;

  function clearPreview() {
    preview.hidden = true;
    preview.removeAttribute('src');
    if (objectURL) URL.revokeObjectURL(objectURL);
    objectURL = null;
  }
  function selection() {
    clearPreview();
    status.textContent = '';
    const file = input.files[0];
    if (!file) return;
    if (file.size > limitMB * 1024 * 1024) {
      status.textContent = `La imagen debe pesar como máximo ${limitMB} MB.`;
      return;
    }
    objectURL = URL.createObjectURL(file);
    preview.src = objectURL;
    preview.hidden = false;
  }
  input.addEventListener('change', selection);
  preview.addEventListener('error', () => { preview.hidden = true; });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    const file = input.files[0];
    if (!file) { status.textContent = 'Selecciona una fotografía.'; return; }
    if (file.size > limitMB * 1024 * 1024) {
      status.textContent = `La imagen debe pesar como máximo ${limitMB} MB.`;
      return;
    }
    const selectedRiver = river;
    const body = new FormData();
    body.append('file', file);
    busy = true;
    submit.disabled = true;
    submit.textContent = 'Subiendo imagen…';
    status.textContent = 'Validando y guardando la fotografía…';
    const active = new AbortController();
    controller = active;
    const timeout = setTimeout(() => active.abort(), 30000);
    try {
      const headers = { 'X-IoT-Key': key.value };
      key.value = '';
      const response = await fetch(`/api/analysis-tests?river_id=${encodeURIComponent(selectedRiver)}`,
        { method: 'POST', body, headers, signal: active.signal });
      const result = await response.json();
      if (stopped) return;
      if (!response.ok) {
        const message = response.status === 401 ? 'Clave incorrecta. Usa el valor de IOT_KEY de tu archivo .env.'
          : response.status === 503 ? 'La subida no está habilitada. Configura IOT_KEY en el servidor.'
          : typeof result.detail === 'string' ? result.detail : 'No se pudo guardar la prueba. Revisa la fotografía.';
        throw new Error(message);
      }
      form.reset();
      clearPreview();
      status.textContent = 'Prueba guardada. El informe muestra el estado y se actualizará al terminar el análisis.';
      onCreated(result, submit);
    } catch (error) {
      if (!stopped) status.textContent = error.name === 'AbortError'
        ? 'La subida se interrumpió. Revisa Pruebas manuales antes de repetir el envío.'
        : error.message === 'Failed to fetch' ? 'No se pudo conectar con el servidor. Inténtalo de nuevo.' : error.message;
    } finally {
      clearTimeout(timeout);
      key.value = '';
      busy = false;
      submit.disabled = false;
      submit.textContent = 'Analizar imagen';
    }
  });
  window.addEventListener('pagehide', () => { stopped = true; controller?.abort(); key.value = ''; clearPreview(); });
  window.addEventListener('pageshow', event => { if (event.persisted) { stopped = false; selection(); } });
  return {
    selectRiver(value) {
      river = value;
      document.getElementById('analysis-test-river').textContent = 'río Chillón';
    },
  };
}
