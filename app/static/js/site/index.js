import { initAuth, renderAccount } from './auth.js';
import { initAlerts } from './alerts.js';
import { initAdmin } from './admin.js';
import { initPublicReports } from './reports.js';
import { initAccountPages } from './account-pages.js';
import { initHeader } from './header.js';
import { initPWA } from './pwa.js';
import { initNearbyNotifications } from './nearby-notifications.js';

document.addEventListener('click', event => {
  const button = event.target.closest('[data-close-dialog]');
  if (button) document.getElementById(button.dataset.closeDialog)?.close();
});
initPWA();
const sessionReady = initAuth();
initHeader();
initNearbyNotifications();
initAlerts();
initAccountPages();
sessionReady.then(initAdmin);
initPublicReports(renderAccount);
