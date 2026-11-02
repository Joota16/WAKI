"""Descarga explícita del eje cartografiado del río Chillón desde OSM.

No se ejecuta al arrancar WAKI. También acepta una respuesta Overpass local.
Las geometrías se conservan por vía, sin unir extremos ni suavizar el cauce.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import unicodedata
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
ENDPOINT = "https://overpass-api.de/api/interpreter"
RIVERS = {
    11643078: ("chillon", "Río Chillón", (-11.932, -77.065)),
}
QUERY = "[out:json][timeout:60]; relation(id:11643078); out body geom;"


def normalized(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", value.casefold())
                   if unicodedata.category(char) != "Mn")


def build_geojson(document: dict) -> dict:
    if document.get("remark"):
        raise ValueError(f"La fuente no devolvió una respuesta completa: {document['remark']}")
    relations = {element["id"]: element for element in document.get("elements", [])
                 if element.get("type") == "relation"}
    features = []
    for relation_id, (key, name, target) in RIVERS.items():
        relation = relations.get(relation_id)
        if relation is None:
            raise ValueError(f"Falta la relación de {name}: {relation_id}.")
        tags = relation.get("tags", {})
        if tags.get("type") != "waterway" or tags.get("waterway") != "river" or normalized(tags.get("name", "")) != normalized(name):
            raise ValueError(f"La relación {relation_id} no corresponde al río esperado.")
        lines, way_ids = [], []
        for member in relation.get("members", []):
            if member.get("type") != "way" or member.get("role", "") not in {"", "main_stream"}:
                continue
            if member["ref"] in way_ids:
                continue
            geometry = member.get("geometry", [])
            if len(geometry) < 2:
                raise ValueError(f"Geometría incompleta en la vía {member['ref']}.")
            coordinates = []
            for point in geometry:
                longitude, latitude = point.get("lon"), point.get("lat")
                if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (longitude, latitude)):
                    raise ValueError("La geometría contiene coordenadas inválidas.")
                if not (-78 < longitude < -75 and -13 < latitude < -10):
                    raise ValueError("Las coordenadas no corresponden al ámbito esperado de Lima.")
                coordinates.append([longitude, latitude])  # GeoJSON: longitud, latitud.
            lines.append(coordinates)
            way_ids.append(member["ref"])
        if not lines:
            raise ValueError(f"No se encontró el cauce principal de {name}.")
        # El foco del marcador se toma de un nodo real del cauce cerca del tramo del tablero.
        focus = min((point for line in lines for point in line), key=lambda point:
                    (point[1] - target[0]) ** 2 + ((point[0] - target[1]) * math.cos(math.radians(target[0]))) ** 2)
        features.append({
            "type": "Feature", "id": key,
            "properties": {"id": key, "name": name, "osm_relation_id": relation_id,
                           "source_url": f"https://www.openstreetmap.org/relation/{relation_id}",
                           "osm_way_ids": way_ids, "vertex_count": sum(map(len, lines)),
                           "view_center": focus},
            "geometry": {"type": "MultiLineString", "coordinates": lines},
        })
    return {
        "type": "FeatureCollection",
        "attribution": "© OpenStreetMap contributors",
        "license": {"name": "Open Database License (ODbL) 1.0",
                    "url": "https://opendatacommons.org/licenses/odbl/1-0/"},
        "source": "OpenStreetMap / Overpass API",
        "source_timestamp": document.get("osm3s", {}).get("timestamp_osm_base"),
        "features": features,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Respuesta JSON de Overpass ya descargada; evita la consulta de red.")
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--output", type=Path, default=ROOT / "app/static/data/rivers.geojson")
    args = parser.parse_args()
    if args.input:
        raw = args.input.read_bytes()
    else:
        url = args.endpoint + "?" + urllib.parse.urlencode({"data": QUERY})
        request = urllib.request.Request(url, headers={"User-Agent": "WAKI/0.1 river-map-import", "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=75) as response:
            raw = response.read(20 * 1024 * 1024 + 1)
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("La respuesta supera el tamaño esperado.")
    result = build_geojson(json.loads(raw))
    result["imported_at"] = datetime.now(timezone.utc).isoformat()
    result["source_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
        temporary.replace(args.output)
    finally:
        temporary.unlink(missing_ok=True)
    for feature in result["features"]:
        properties = feature["properties"]
        print(f"{properties['name']}: {len(properties['osm_way_ids'])} tramos, {properties['vertex_count']} puntos")
    print(args.output)


if __name__ == "__main__":
    main()
