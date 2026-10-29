/** Reportes guardados: listado reciente, resumen y datos reales para el mapa. */
export function initRecentReports(riverMap) {
  const list = document.getElementById('dashboard-saved-reports');
  const latest = document.getElementById('latest-saved-report');
  const count = document.getElementById('reports-count-label');
  const refresh = document.getElementById('refresh-saved-reports');
  const dateFormat = new Intl.DateTimeFormat('es-PE', {
    timeZone: 'America/Lima', dateStyle: 'short', timeStyle: 'short',
  });
  let loading = false;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function reportLink(report, compact = false) {
    const link = element('a', 'flex gap-3 items-start p-3 rounded-xl border border-slate-200 hover:bg-sky-50 min-w-0');
    link.href = report.detail_url;
    if (report.photos.length) {
      const photo = element('img', 'w-16 h-16 object-cover rounded-lg shrink-0');
      photo.src = report.photos[0].url;
      photo.alt = `Fotografía de ${report.river_section}`;
      photo.loading = 'lazy';
      link.append(photo);
    }
    const info = element('div', 'flex-1 min-w-0 text-xs flex flex-col gap-1');
    info.append(element('p', 'font-bold text-slate-800 break-words', `${report.river_section} · ${report.district}`));
    if (!compact) info.append(element('p', 'text-slate-600 break-words', report.reference));
    const date = element('time', 'text-slate-500', `${dateFormat.format(new Date(report.created_at))} (Lima)`);
    date.dateTime = report.created_at;
    info.append(date);
    info.append(element('p', 'text-slate-500', `${report.photos.length} ${report.photos.length === 1 ? 'foto' : 'fotos'} · Pendiente de verificación`));
    info.append(element('span', 'text-sky-600 font-semibold', 'Ver reporte y fotos →'));
    link.append(info);
    return link;
  }

  async function load() {
    if (loading) return;
    loading = true;
    refresh.disabled = true;
    list.setAttribute('aria-busy', 'true');
    list.textContent = 'Cargando reportes guardados…';
    latest.textContent = 'Cargando reportes guardados…';
    try {
      const response = await fetch('/api/reports?limit=6&offset=0', { cache: 'no-store' });
      if (!response.ok) throw new Error('No se pudo consultar el listado.');
      const result = await response.json();
      if (!Array.isArray(result.items) || !Number.isInteger(result.total)) throw new Error('Respuesta inválida.');
      list.replaceChildren();
      latest.replaceChildren();
      count.textContent = `Ver ${result.total} ${result.total === 1 ? 'reporte' : 'reportes'}`;
      if (!result.items.length) {
        list.append(element('p', 'text-slate-500 py-4', 'Todavía no hay reportes registrados.'));
        const create = element('a', 'text-sky-600 font-semibold hover:underline', 'Registrar el primer reporte');
        create.href = '/reportar';
        list.append(create);
        latest.textContent = 'Todavía no hay reportes registrados.';
      } else {
        list.append(element('p', 'text-xs text-slate-500', `Mostrando los ${result.items.length} más recientes de ${result.total}, de Chillón y Rímac.`));
        result.items.forEach(report => list.append(reportLink(report)));
        latest.append(reportLink(result.items[0], true));
      }
      riverMap?.setReports(result.items);
    } catch {
      list.replaceChildren(element('p', 'text-red-700 py-3', 'No se pudieron cargar los reportes. Pulsa «Actualizar» para volver a intentarlo.'));
      latest.textContent = 'No se pudieron consultar los reportes guardados.';
      count.textContent = 'Ver listado';
      riverMap?.setReports([]);
    } finally {
      loading = false;
      refresh.disabled = false;
      list.setAttribute('aria-busy', 'false');
    }
  }

  refresh.addEventListener('click', load);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
  load();
}
