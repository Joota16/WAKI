/** Muestra y valida la descripción únicamente cuando se selecciona «Otros». */
export function initSituations() {
  const form = document.getElementById('citizenReportForm');
  const other = document.getElementById('situation-other');
  const field = document.getElementById('situation-other-field');
  const description = document.getElementById('situation-other-description');

  function validate() {
    description.setCustomValidity(other.checked && !description.value.trim()
      ? 'Describe la otra situación que observas.' : '');
  }
  function update() {
    field.hidden = !other.checked;
    description.disabled = !other.checked;
    description.required = other.checked;
    other.setAttribute('aria-expanded', String(other.checked));
    validate();
  }
  other.addEventListener('change', () => {
    update();
    if (other.checked) description.focus();
  });
  description.addEventListener('input', validate);
  form.addEventListener('reset', () => queueMicrotask(update));
  update();
}
