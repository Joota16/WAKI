import { message, requestJSON } from './utils.js';

let session = { user: null, csrf_token: null }, generation = 0;
export const getSession = () => session;

export function renderAccount() {
  const admin = session.user?.role === 'admin';
  document.querySelectorAll('[data-open-auth]').forEach(node => { node.hidden = !!session.user; });
  document.querySelectorAll('[data-account-menu]').forEach(node => { node.hidden = !session.user; });
  document.querySelectorAll('[data-account-name]').forEach(node => { node.textContent = session.user?.username || 'Cuenta'; });
  document.querySelectorAll('[data-account-role]').forEach(node => { node.textContent = admin ? 'Administrador' : 'Usuario'; });
  document.querySelectorAll('[data-admin-only]').forEach(node => { node.hidden = !admin; });
  document.body.dataset.role = session.user?.role || 'guest';
  document.querySelectorAll('[data-protected-page]').forEach(node => {
    const allowed = !!session.user && (node.dataset.protectedPage !== 'admin' || admin);
    node.hidden = !allowed;
    document.getElementById('page-access-gate').hidden = allowed;
    node.inert = !allowed;
  });
}

export function adopt(value) {
  ++generation;
  session = value;
  renderAccount();
  document.dispatchEvent(new CustomEvent('session-changed', { detail: session.user }));
}

export async function refreshSession() {
  const current = ++generation;
  try {
    const value = await requestJSON('/api/auth/me');
    if (current === generation) adopt(value);
  } catch {
    if (current === generation) adopt({ user: null, csrf_token: null });
  }
}

export async function authenticatedJSON(url, options = {}) {
  const headers = { ...options.headers };
  if (options.body) headers['Content-Type'] = 'application/json';
  if (options.method && options.method !== 'GET') headers['X-CSRF-Token'] = session.csrf_token || '';
  try { return await requestJSON(url, { ...options, headers }); }
  catch (error) {
    if (error.status === 401) {
      ++generation;
      adopt({ user: null, csrf_token: null });
      message('Tu sesión terminó. Puedes seguir usando el tablero y reportar sin cuenta.');
    }
    throw error;
  }
}

export function initAuth() {
  document.addEventListener('click', async event => {
    if (event.target.closest('[data-logout]')) {
      try {
        await authenticatedJSON('/api/auth/logout', { method: 'POST' });
        ++generation;
        adopt({ user: null, csrf_token: null });
        document.dispatchEvent(new Event('reports-changed'));
        message('Sesión cerrada. El tablero y el formulario siguen disponibles.');
      } catch (failure) { message(failure.message); }
    }
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshSession(); });
  const checkSession = () => { if (!document.hidden) refreshSession(); };
  let timer = setInterval(checkSession, 60000);
  window.addEventListener('pagehide', () => clearInterval(timer));
  window.addEventListener('pageshow', event => {
    if (event.persisted) { timer = setInterval(checkSession, 60000); refreshSession(); }
  });
  return refreshSession();
}
