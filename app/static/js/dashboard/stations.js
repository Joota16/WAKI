import { HYDROLOGICAL_STATIONS } from './stations-data.js';

/** Capa de estaciones independiente de los trazados y reportes ciudadanos. */
export function addHydrologicalStations(L, map) {
  const layer = L.featureGroup().addTo(map);
  const markers = new Map();

  for (const station of HYDROLOGICAL_STATIONS) {
    const popup = document.createElement('div');
    popup.className = 'hydro-station-popup';
    const title = document.createElement('h3');
    title.textContent = station.name;
    const type = document.createElement('p');
    type.textContent = 'Estación hidrológica';
    const coordinates = document.createElement('p');
    coordinates.className = 'hydro-station-coordinates';
    coordinates.textContent = `Latitud: ${station.latLng[0]} · Longitud: ${station.latLng[1]}`;
    const link = document.createElement('a');
    const [latitude, longitude] = station.latLng;
    link.href = `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=15/${latitude}/${longitude}`;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Abrir ubicación en el mapa';
    popup.append(title, type, coordinates, link);

    const marker = L.marker(station.latLng, {
      title: station.name,
      zIndexOffset: 600,
      icon: L.divIcon({
        className: 'hydro-station-marker',
        html: '<span class="hydro-station-symbol" aria-hidden="true">EH</span>',
        iconSize: [32, 32], iconAnchor: [16, 16], popupAnchor: [0, -16],
      }),
    }).addTo(layer).bindPopup(popup, { maxWidth: 250 }).bindTooltip(station.name, {
      permanent: true, direction: 'top', offset: [0, -18], className: 'hydro-station-label',
    });
    const icon = marker.getElement();
    icon.dataset.stationId = station.id;
    icon.setAttribute('aria-label', `Estación hidrológica ${station.name}`);
    markers.set(station.id, marker);
  }

  return {
    showAll(options = {}) {
      map.fitBounds(layer.getBounds(), {
        paddingTopLeft: [72, 125], paddingBottomRight: [72, 180], maxZoom: 13, ...options,
      });
    },
    focus(id) {
      const marker = markers.get(id);
      if (!marker) return;
      map.setView(marker.getLatLng(), 13);
      marker.openPopup();
    },
  };
}
