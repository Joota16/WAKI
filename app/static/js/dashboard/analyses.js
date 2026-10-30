import { initAnalysisDialog } from './analysis-dialog.js';
import { initAnalysisUpload } from './analysis-upload.js';

const formatDate = value => new Intl.DateTimeFormat('es-PE', {
  timeZone: 'America/Lima', dateStyle: 'short', timeStyle: 'medium',
}).format(new Date(value));

export function initAnalyses() {
  const reportDialog = initAnalysisDialog();
  const panel = document.getElementById('tab-panel-imagenes');
  const cameras = JSON.parse(panel.dataset.cameras);
  const gallery = document.getElementById('analyses-gallery');
  const status = document.getElementById('analyses-status');
  const previous = document.getElementById('analyses-previous');
  const next = document.getElementById('analyses-next');
  const page = document.getElementById('analyses-page');
  const views = new Map();
  let camera = null, river = null, source = 'iot', offset = 0, sequence = 0, timer = null, controller = null, signature = '';
  const limit = 6;
  const upload = initAnalysisUpload({ onCreated(item, trigger) {
    if (item.river_id === river) {
      source = 'test';
      updateSources();
      resetGallery();
    }
    reportDialog.open(item.id, trigger);
  } });

  function card(item) {
    const element = document.getElementById('analysis-card-template').content.firstElementChild.cloneNode(true);
    const find = name => element.querySelector(`[data-analysis-${name}]`);
    const image = find('image'), imageStatus = find('image-status'), toggle = find('toggle');
    find('camera').textContent = item.source === 'test' ? 'Prueba manual' : item.camera_id;
    const time = find('time');
    time.dateTime = item.captured_at || item.received_at;
    time.textContent = `${item.source === 'test' ? 'Subida' : item.captured_at ? 'Capturada' : 'Recibida'}: ${formatDate(time.dateTime)} (Lima)`;
    find('state').textContent = item.status_label;
    find('message').textContent = item.message;
    const water = item.water_fraction == null ? 'Segmentación no disponible'
      : `${(item.water_fraction * 100).toFixed(1)} % de píxeles de agua`;
    const objects = item.objects_available ? `${item.candidate_count} ${item.candidate_count === 1 ? 'candidato' : 'candidatos'} para revisar` : 'Detección de objetos no disponible';
    find('summary').textContent = ['analyzed', 'partial'].includes(item.status) ? `${water} · ${objects}` : '';
    find('report').addEventListener('click', event => reportDialog.open(item.id, event.currentTarget));
    let original = views.get(item.id) === 'original' || !item.overlay_url;
    function show() {
      image.hidden = true;
      imageStatus.hidden = false;
      imageStatus.textContent = 'Cargando fotografía…';
      image.alt = original ? 'Fotografía original de la captura' : 'Resultado de IA de la captura; pendiente de revisión';
      image.src = original ? item.original_url : item.overlay_url;
      toggle.textContent = original ? 'Ver análisis' : 'Ver original';
      toggle.disabled = !item.overlay_url;
      toggle.hidden = !item.overlay_url;
    }
    image.addEventListener('load', () => { image.hidden = false; imageStatus.hidden = true; });
    image.addEventListener('error', () => {
      image.hidden = true;
      imageStatus.hidden = false;
      imageStatus.textContent = 'No se pudo cargar esta imagen. Abre el informe para consultar la captura.';
    });
    toggle.addEventListener('click', () => {
      original = !original;
      views.set(item.id, original ? 'original' : 'analysis');
      show();
    });
    show();
    return element;
  }

  async function refresh() {
    const current = ++sequence;
    controller?.abort();
    const activeController = new AbortController();
    controller = activeController;
    const timeout = setTimeout(() => activeController.abort(), 10000);
    try {
      const endpoint = source === 'test' ? `/api/analysis-tests?river_id=${encodeURIComponent(river)}&`
        : `/api/cameras/${encodeURIComponent(camera)}/analyses?`;
      const response = await fetch(`${endpoint}limit=${limit}&offset=${offset}`,
        { signal: activeController.signal, cache: 'no-store' });
      if (!response.ok) throw new Error('No se pudieron consultar los análisis.');
      const data = await response.json();
      if (sequence !== current) return;
      if (offset && !data.items.length) {
        offset = data.total ? Math.floor((data.total - 1) / limit) * limit : 0;
        signature = '';
        return refresh();
      }
      const updated = JSON.stringify(data.items);
      if (signature !== updated) {
        gallery.replaceChildren(...data.items.map(card));
        signature = updated;
      }
      status.textContent = source === 'test'
        ? data.total ? 'Pruebas manuales guardadas. Consulta automática cada 5 segundos.' : 'Todavía no hay pruebas manuales para este río. Puedes subir una imagen arriba.'
        : data.total ? 'Informes de las capturas recibidas. Consulta automática cada 5 segundos.'
          : 'Todavía no hay capturas para analizar en esta cámara. Las nuevas fotografías del ESP32 aparecerán aquí.';
      page.textContent = data.total ? `${offset + 1}–${offset + data.items.length} de ${data.total}` : 'Sin capturas';
      previous.disabled = offset === 0;
      next.disabled = offset + limit >= data.total;
    } catch {
      if (sequence !== current) return;
      status.textContent = 'No se pudieron actualizar los informes de IA. Reintentaremos en unos segundos.';
    } finally {
      clearTimeout(timeout);
      if (sequence === current) schedule();
    }
  }
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(() => document.hidden ? schedule() : refresh(), 5000);
  }
  function changePage(delta) {
    offset = Math.max(0, offset + delta * limit);
    clearTimeout(timer);
    refresh();
  }
  previous.addEventListener('click', () => changePage(-1));
  next.addEventListener('click', () => changePage(1));
  function updateSources() {
    document.querySelectorAll('[data-analysis-source]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.analysisSource === source));
    });
  }
  function resetGallery() {
    ++sequence;
    controller?.abort();
    clearTimeout(timer);
    offset = 0; signature = '';
    gallery.replaceChildren(); views.clear();
    previous.disabled = true; next.disabled = true; page.textContent = '';
    status.textContent = 'Consultando análisis…';
    refresh();
  }
  document.querySelectorAll('[data-analysis-source]').forEach(button => button.addEventListener('click', () => {
    if (source === button.dataset.analysisSource) return;
    source = button.dataset.analysisSource;
    updateSources();
    resetGallery();
  }));
  window.addEventListener('pagehide', () => { ++sequence; controller?.abort(); clearTimeout(timer); });
  window.addEventListener('pageshow', event => { if (event.persisted && camera) refresh(); });
  return {
    selectRiver(value) {
      const selected = cameras[value];
      if (!selected || selected === camera) return;
      camera = selected; river = value;
      upload.selectRiver(value);
      resetGallery();
    },
  };
}
