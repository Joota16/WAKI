export function element(tag, text, className = '') {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  node.className = className;
  return node;
}

export const localTime = value => new Intl.DateTimeFormat('es-PE', {
  timeZone: 'America/Lima', dateStyle: 'short', timeStyle: 'short',
}).format(new Date(value));

export function message(text) {
  const node = document.getElementById('site-message');
  node.textContent = text;
  node.hidden = false;
  clearTimeout(message.timer);
  message.timer = setTimeout(() => { node.hidden = true; }, 7000);
}

export async function requestJSON(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, { cache: 'no-store', credentials: 'same-origin', ...options, signal: controller.signal });
    const data = response.status === 204 ? null : await response.json();
    if (!response.ok) {
      const detail = Array.isArray(data?.detail) ? data.detail.map(item => item.msg).join('\n') : data?.detail;
      const error = new Error(detail || 'No se pudo completar la solicitud.');
      error.status = response.status;
      throw error;
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('La solicitud tardó demasiado. Inténtalo de nuevo.');
    if (error instanceof TypeError) throw new Error('No se pudo conectar con el servidor.');
    throw error;
  } finally { clearTimeout(timeout); }
}
