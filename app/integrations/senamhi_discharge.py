"""Caudales del hidrograma público de SENAMHI, sin ejecutar JavaScript."""
from datetime import datetime, timedelta, timezone
import json
import logging
import re
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from app.integrations.senamhi import InvalidStationData, SenamhiProvider, _normalize, _variable
from app.schemas.hydrology import DischargeBatch, DischargeReading, DischargeStation, DischargeThresholds

logger = logging.getLogger(__name__)

MONITOR_URL = "https://www.senamhi.gob.pe/servicios/?p=monitoreo-hidrologico"
CHART_URL = "https://www.senamhi.gob.pe/mapas/mapa-monitoreohidro/include/mnt-grafica-new.php"
METADATA_URL = "https://idesep.senamhi.gob.pe/geoserver/g_dbphisis/ows"
DISCHARGE_STATIONS = (
    DischargeStation(id="obrajillo", code="47E9F488", name="Obrajillo", river_id="chillon",
                     chart_gap_seconds=3600, source_url=MONITOR_URL),
    DischargeStation(id="puente-magdalena", code="111151", name="Puente Magdalena", river_id="chillon",
                     chart_gap_seconds=14400, source_url=MONITOR_URL),
)


def chart_url_from_metadata(document: dict, station: DischargeStation) -> str:
    features = document.get("features", [])
    if document.get("type") != "FeatureCollection" or len(features) != 1:
        raise InvalidStationData("No se encontró la estación en el catálogo de caudal.")
    feature = features[0]
    properties = feature.get("properties", {})
    if (feature.get("id") != f"estaciones_monitoreo.{station.code}"
            or _normalize(properties.get("nom_estacion", "")) != _normalize(station.name)
            or properties.get("variable") != "C"
            or _normalize(properties.get("nom_cuenca", "")) != "cuenca chillon"):
        raise InvalidStationData("La estación o la variable de caudal no coincide.")
    try:
        published_at = datetime.fromisoformat(properties["fecha_hora"])
        if published_at.tzinfo is None:
            raise ValueError("La fecha del catálogo no tiene zona horaria.")
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidStationData("El catálogo no tiene una fecha de datos válida.") from exc
    # El visor recibe esta fecha UTC y la convierte internamente para consultar.
    return CHART_URL + "?" + urlencode({
        "id": station.code, "fecha_hora": published_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "variable": "CAUDAL", "variable_opcion": "C",
    })


def parse_discharge(html: str, station: DischargeStation, now: datetime | None = None) -> list[DischargeReading]:
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script\s*>", html, flags=re.S | re.I)
    charts = [script for script in scripts if re.search(r"\bvar\s+data\s*=", script)]
    if len(charts) != 1:
        raise InvalidStationData("No se encontró el hidrograma público de caudal.")
    data = _variable(charts[0], "data", next_variable="dataCSV")
    if (not isinstance(data, dict) or data.get("codEstacion") != station.code
            or _normalize(data.get("nomEstacion", "")) != _normalize(station.name)
            or _normalize(data.get("nomRio", "")) != "rio chillon"
            or data.get("variable") != "CAUDAL" or data.get("unidad") != "m3/s"):
        raise InvalidStationData("Estación, río, variable o unidad de caudal inesperada.")
    points = data.get("dato")
    if not isinstance(points, list) or not 1 <= len(points) <= 2000:
        raise InvalidStationData("La fuente no contiene lecturas horarias de caudal.")
    # Los límites pertenecen a cada instante publicado; no se extrapolan a
    # otras fechas ni se confunden con las mediciones de la serie «dato».
    threshold_series = {}
    for source, name in [('amarillo', 'yellow_m3s'), ('naranja', 'orange_m3s'), ('rojo', 'red_m3s')]:
        series = data.get(source)
        values = {}
        if isinstance(series, list) and len(series) <= 2000:
            for point in series:
                if (not isinstance(point, list) or len(point) != 2 or isinstance(point[0], bool)
                        or not isinstance(point[0], int) or point[0] in values):
                    values = {}
                    break
                values[point[0]] = point[1]
        threshold_series[name] = values
    now = now or datetime.now(timezone.utc)
    readings = []
    timestamps = []
    for point in points:
        try:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("Punto incompleto")
            stamp, value = point
            if isinstance(stamp, bool) or not isinstance(stamp, int) or not 946684800000 <= stamp < 4102444800000:
                raise ValueError("Fecha fuera del formato en milisegundos")
            if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int))):
                raise ValueError("Caudal inválido")
            # Highcharts muestra estas marcas como hora de Lima codificada como UTC.
            # Se conserva la hora que ve el usuario en el visor y se almacena en UTC real.
            local_time = datetime.fromtimestamp(stamp / 1000, timezone.utc).replace(tzinfo=ZoneInfo("America/Lima"))
            observed_at = local_time.astimezone(timezone.utc)
            limits = {name: series.get(stamp) for name, series in threshold_series.items()}
            thresholds = None
            if all(isinstance(limit, (int, float)) and not isinstance(limit, bool) for limit in limits.values()):
                try:
                    thresholds = DischargeThresholds(**limits)
                except ValueError:
                    pass  # Un umbral incompleto o inválido no elimina un caudal válido.
            readings.append(DischargeReading(observed_at=observed_at, discharge_m3s=value, thresholds=thresholds))
            timestamps.append(stamp)
        except (ValueError, TypeError, OverflowError) as exc:
            raise InvalidStationData(f"La serie contiene una lectura de caudal inválida: {exc}") from exc
    if len(set(timestamps)) != len(timestamps) or data.get("fechaHora") != timestamps:
        raise InvalidStationData("Las fechas de caudal son duplicadas o no coinciden con la serie.")
    # Validar primero toda la serie; una fecha adelantada no debe descartar
    # observaciones válidas ni permitir que pasen valores o fechas corruptos.
    cutoff = now + timedelta(minutes=5)
    future = [item for item in readings if item.observed_at > cutoff]
    if future:
        logger.warning(
            "Caudal SENAMHI %s: se omiten %s lecturas futuras; primera=%s, última=%s, consulta=%s",
            station.code, len(future), min(item.observed_at for item in future).isoformat(),
            max(item.observed_at for item in future).isoformat(), now.isoformat(),
        )
        readings = [item for item in readings if item.observed_at <= cutoff]
        if not any(item.discharge_m3s is not None for item in readings):
            raise InvalidStationData("La fuente no contiene caudales válidos sin fechas futuras.")
    return sorted(readings, key=lambda item: item.observed_at)


class SenamhiDischargeProvider(SenamhiProvider):
    async def fetch(self, station: DischargeStation) -> DischargeBatch:
        metadata_url = METADATA_URL + "?" + urlencode({
            "service": "WFS", "version": "1.0.0", "request": "GetFeature",
            "typeName": "g_dbphisis:estaciones_monitoreo", "featureID": f"estaciones_monitoreo.{station.code}",
            "outputFormat": "application/json",
        })
        metadata = json.loads(await self.get_public_document(metadata_url, "application/json"))
        source_url = chart_url_from_metadata(metadata, station)
        html = await self.get_public_document(source_url)
        return DischargeBatch(readings=parse_discharge(html.decode("utf-8"), station), source_url=source_url)
