import { getSession } from '../site/auth.js';
import { initPhoneInput } from '../site/phone-input.js';

export function initReportPhone() {
  const input = document.getElementById('report-phone');
  const form = document.getElementById('citizenReportForm');
  const normalize = initPhoneInput(input);
  let automaticValue = '', manual = false, applying = false;

  function synchronize() {
    if (manual && input.value !== automaticValue) return;
    const value = getSession().user?.phone || '';
    if (input.value !== value) {
      applying = true;
      input.value = value;
      normalize();
      // Cambia también la clave del envío si cambió el contacto del borrador.
      input.dispatchEvent(new Event('input', { bubbles: true }));
      applying = false;
    }
    automaticValue = value; manual = false;
  }
  input.addEventListener('input', () => { if (!applying) manual = true; });
  document.addEventListener('session-changed', synchronize);
  form.addEventListener('reset', () => queueMicrotask(() => { manual = false; synchronize(); normalize(); }));
  synchronize();
}
