import { adopt, authenticatedJSON } from './auth.js';
import { requestJSON } from './utils.js';

export function initAccountPages() {
  const access = document.getElementById('auth-form');
  access?.addEventListener('submit', async event => {
    event.preventDefault();
    const submit = document.getElementById('auth-submit');
    if (submit.disabled) return;
    const error = document.getElementById('auth-error');
    const values = Object.fromEntries(new FormData(access));
    error.textContent = '';
    if (access.dataset.mode === 'register' && values.password !== values.password_confirmation) {
      error.textContent = 'Las contraseñas no coinciden.'; return;
    }
    submit.disabled = true;
    try {
      const session = await requestJSON(`/api/auth/${access.dataset.mode}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values),
      });
      adopt(session);
      const destination = access.dataset.destination;
      const allowed = ['/', '/administrar', '/admin/avisos', '/admin/reportes'].includes(destination);
      window.location.assign(allowed && (!destination.startsWith('/admin/') || session.user.role === 'admin') ? destination : '/');
    } catch (failure) { error.textContent = failure.message; }
    finally { access.querySelectorAll('[type="password"]').forEach(input => { input.value = ''; }); submit.disabled = false; }
  });

  const passwordForm = document.getElementById('password-form');
  passwordForm?.addEventListener('submit', async event => {
    event.preventDefault();
    const submit = passwordForm.querySelector('[type="submit"]');
    if (submit.disabled) return;
    const error = document.getElementById('password-error');
    const values = Object.fromEntries(new FormData(passwordForm));
    error.textContent = '';
    if (values.new_password !== values.password_confirmation) {
      error.textContent = 'Las contraseñas nuevas no coinciden.'; return;
    }
    submit.disabled = true;
    try {
      await authenticatedJSON('/api/auth/password', { method: 'POST', body: JSON.stringify(values) });
      adopt({ user: null, csrf_token: null });
      window.location.assign('/ingresar?password_changed=1');
    } catch (failure) { error.textContent = failure.message; }
    finally { passwordForm.reset(); submit.disabled = false; }
  });
  window.addEventListener('pagehide', () => {
    document.querySelectorAll('#auth-form [type="password"], #password-form [type="password"]').forEach(input => { input.value = ''; });
  });
}
