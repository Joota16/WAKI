import { initAnalysisViewer } from './viewer.js';

const panel = document.getElementById('analysis-detail');
let viewer = initAnalysisViewer(panel, { onStatusChange: () => location.reload() });
window.addEventListener('pagehide', () => viewer.destroy());
window.addEventListener('pageshow', event => {
  if (event.persisted) viewer = initAnalysisViewer(panel, { onStatusChange: () => location.reload() });
});
