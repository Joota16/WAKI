import { message } from './utils.js';

/** Instalación de WAKI; las páginas y los datos siempre se consultan por red. */
export function initPWA() {
  const button = document.getElementById('pwa-install-button');
  const instructions = document.getElementById('pwa-install-dialog');
  if (!button || !instructions) return;

  const standalone = window.matchMedia('(display-mode: standalone)');
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const safari = /Safari/.test(navigator.userAgent) && !/CriOS|FxiOS|EdgiOS|OPiOS/.test(navigator.userAgent);
  let deferred = null, prompting = false, installed = false;

  function isStandalone() { return standalone.matches || navigator.standalone === true; }
  function update() {
    button.hidden = !window.isSecureContext || installed || isStandalone() || (!deferred && !ios);
    button.disabled = prompting;
    if ((installed || isStandalone()) && instructions.open) instructions.close();
  }

  window.addEventListener('beforeinstallprompt', event => {
    if (installed || isStandalone() || typeof event.prompt !== 'function') return;
    event.preventDefault();
    deferred = event;
    update();
  });
  window.addEventListener('appinstalled', () => {
    installed = true;
    deferred = null;
    update();
  });
  standalone.addEventListener('change', update);

  button.addEventListener('click', async () => {
    if (prompting || installed || isStandalone()) return;
    if (!deferred) {
      if (ios) {
        document.getElementById('pwa-open-safari').hidden = safari;
        if (!instructions.open) instructions.showModal();
      }
      return;
    }
    const event = deferred;
    deferred = null;
    prompting = true;
    update();
    try {
      await event.prompt();
      const choice = await event.userChoice;
      if (choice.outcome === 'accepted') installed = true;
    } catch {
      message('No se pudo abrir la instalación. Usa la opción Instalar del menú de tu navegador.');
    } finally {
      prompting = false;
      update();
    }
  });
  update();
}
