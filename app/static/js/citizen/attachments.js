/** Selección, validación y previsualización local; el servidor vuelve a validar. */
export function initAttachments() {
  const form = document.getElementById('citizenReportForm');
  const picker = document.getElementById('citizenPhotoInput');
  const camera = document.getElementById('citizenCameraInput');
  const dropzone = document.getElementById('photoDropzone');
  const list = document.getElementById('photoPreviewList');
  const error = document.getElementById('photoError');
  const maxPhotos = Number(form.dataset.maxPhotos);
  const maxBytes = Number(form.dataset.maxUploadMb) * 1024 * 1024;
  const maxPixels = Number(form.dataset.maxImagePixels);
  let items = [];
  let work = Promise.resolve();
  let pending = 0;
  function render() {
    list.replaceChildren();
    document.getElementById('photoCount').textContent = items.length
      ? `${items.length} ${items.length === 1 ? 'fotografía lista' : 'fotografías listas'} para enviar`
      : 'Aún no has seleccionado fotografías.';
    for (const item of items) {
      const card = document.createElement('div');
      card.className = 'photo-preview';
      const image = document.createElement('img');
      image.src = item.url;
      image.alt = `Vista previa de ${item.file.name}`;
      const description = document.createElement('div');
      description.className = 'photo-preview-description';
      const name = document.createElement('span');
      name.textContent = item.file.name;
      const size = document.createElement('small');
      size.textContent = `${(item.file.size / 1024 / 1024).toFixed(2)} MB`;
      description.append(name, size);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = 'Quitar';
      remove.setAttribute('aria-label', `Quitar ${item.file.name}`);
      remove.addEventListener('click', () => {
        items = items.filter(candidate => candidate !== item);
        URL.revokeObjectURL(item.url);
        render();
        form.dispatchEvent(new Event('change', { bubbles: true }));
      });
      card.append(image, description, remove);
      list.append(card);
    }
  }
  function add(files) {
    if (document.getElementById('reportFields').disabled || !files.length) return;
    pending += 1;
    document.getElementById('photoValidationStatus').textContent = 'Comprobando fotografías…';
    work = work.then(async () => {
      const errors = [];
      for (const file of files) {
        if (items.length >= maxPhotos) { errors.push(`Puedes adjuntar como máximo ${maxPhotos} fotografías.`); break; }
        if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
          errors.push(`${file.name}: usa JPEG, PNG o WebP. No se admiten videos ni HEIC.`); continue;
        }
        if (!file.size || file.size > maxBytes) {
          errors.push(`${file.name}: el tamaño debe estar entre 1 byte y ${form.dataset.maxUploadMb} MB.`); continue;
        }
        if (items.some(item => item.file.name === file.name && item.file.size === file.size && item.file.lastModified === file.lastModified)) continue;
        let bitmap;
        try {
          bitmap = await createImageBitmap(file);
          if (bitmap.width * bitmap.height > maxPixels) {
            errors.push(`${file.name}: reduce la resolución de esta fotografía.`); continue;
          }
          items.push({ file, url: URL.createObjectURL(file) });
        } catch {
          errors.push(`${file.name}: no se pudo leer la fotografía. Prueba con otro archivo.`);
        } finally {
          bitmap?.close();
        }
      }
      error.textContent = errors.join(' ');
      error.hidden = !errors.length;
      render();
    }).finally(() => {
      pending -= 1;
      document.getElementById('photoValidationStatus').textContent = pending ? 'Comprobando fotografías…' : '';
    });
  }
  for (const input of [picker, camera]) {
    input.addEventListener('change', () => { add([...input.files]); input.value = ''; });
  }
  for (const name of ['dragenter', 'dragover']) {
    dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.add('is-dragging'); });
  }
  for (const name of ['dragleave', 'drop']) {
    dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.remove('is-dragging'); });
  }
  dropzone.addEventListener('drop', event => add([...event.dataTransfer.files]));
  render();
  return {
    get pending() { return pending > 0; },
    files: () => items.map(item => item.file),
    async restore(files) { this.clear(); add(files); await work; },
    clear() {
      items.forEach(item => URL.revokeObjectURL(item.url));
      items = []; picker.value = camera.value = ''; error.hidden = true; render();
    },
  };
}
