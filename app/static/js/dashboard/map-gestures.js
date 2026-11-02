/** Un dedo desplaza la página; Leaflet conserva el movimiento y zoom con dos. */
export function configureMapGestures(map) {
  const touchPointer = window.matchMedia('(pointer: coarse)');
  const container = map.getContainer();
  const hint = document.createElement('p');
  hint.className = 'map-gesture-hint';
  hint.textContent = 'Usa dos dedos para mover el mapa';
  hint.hidden = true;
  container.parentElement.append(hint);
  let hideTimer;

  function hideHint() {
    window.clearTimeout(hideTimer);
    hint.hidden = true;
  }

  function updateDragging() {
    hideHint();
    if (touchPointer.matches) map.dragging.disable();
    else map.dragging.enable();
  }

  function onTouchStart(event) {
    hideHint();
    if (!touchPointer.matches || event.touches.length !== 1) return;
    hint.hidden = false;
    hideTimer = window.setTimeout(hideHint, 1800);
  }

  // Sin cancelar eventos: el navegador desplaza la página con un dedo y el
  // manejador nativo touchZoom de Leaflet recibe los gestos de dos dedos.
  container.addEventListener('touchstart', onTouchStart, { passive: true });
  touchPointer.addEventListener('change', updateDragging);
  updateDragging();

  map.on('unload', () => {
    hideHint();
    container.removeEventListener('touchstart', onTouchStart);
    touchPointer.removeEventListener('change', updateDragging);
    hint.remove();
  });
}
