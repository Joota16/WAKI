"""Lee la serie pública del gráfico; no accede a tablas protegidas por CAPTCHA."""
import asyncio
from datetime import date, datetime
import json
import re
import unicodedata
from zoneinfo import ZoneInfo

import httpx

from app.schemas.hydrology import DailyLevel, HydrologicalStation

MAGDALENA = HydrologicalStation(
    code="111151", name="Puente Magdalena", river_id="chillon",
    source_url="https://www.senamhi.gob.pe/mapas/mapa-estaciones-ms/map_red_graf.php?cod=111151",
)
STATIONS = {"chillon": MAGDALENA}


class InvalidStationData(ValueError):
    pass


def _variable(script: str, name: str, *, next_variable: str | None = None):
    assignments = list(re.finditer(r"\bvar\s+" + re.escape(name) + r"\s*=\s*", script))
    if len(assignments) != 1:
        raise InvalidStationData(f"La fuente cambió el campo {name}.")
    try:
        # Solo JSON; nunca se evalúa JavaScript de la fuente.
        raw = script[assignments[0].end():]
        value, end = json.JSONDecoder().raw_decode(raw)
        tail = raw[end:]
        terminated = tail.lstrip().startswith(";")
        # El visor de caudal usa salto de línea y declaración siguiente (sin ;).
        if next_variable:
            terminated = terminated or bool(re.match(r"[ \t]*\r?\n\s*var\s+" + re.escape(next_variable) + r"\s*=", tail))
        if not terminated:
            raise ValueError("La fuente aplica una transformación no reconocida.")
        return value
    except (ValueError, TypeError) as exc:
        raise InvalidStationData(f"Campo {name} ilegible.") from exc


def _normalize(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", value.casefold())
                   if unicodedata.category(char) != "Mn")


def parse_daily_levels(html: str, station: HydrologicalStation, today: date | None = None) -> list[DailyLevel]:
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script\s*>", html, flags=re.S | re.I)
    chart = [script for script in scripts if re.search(r"\bvar\s+datosNivel\s*=", script)]
    if len(chart) != 1:
        raise InvalidStationData("No se encontró la serie pública de niveles.")
    script = chart[0]
    title, subtitle, metric = (_variable(script, key) for key in ("titulo", "subtitulo", "nombreNivel"))
    if not all(isinstance(value, str) for value in (title, subtitle, metric)):
        raise InvalidStationData("Identificación de estación inválida.")
    if (_normalize(title).strip() != f"estacion: {_normalize(station.name)}"
            or not re.search(r"codigo:\s*" + re.escape(station.code) + r"\b", _normalize(subtitle))
            or _normalize(metric) != "nivel promedio diario (m)"):
        raise InvalidStationData("La estación o la unidad no corresponde a la fuente configurada.")
    dates, values = (_variable(script, key) for key in ("categorias", "datosNivel"))
    if (not isinstance(dates, list) or not isinstance(values, list)
            or not 1 <= len(dates) <= 400 or len(dates) != len(values)):
        raise InvalidStationData("La serie tiene fechas y valores incompatibles.")
    today = today or datetime.now(ZoneInfo("America/Lima")).date()
    readings = []
    for day, level in zip(dates, values):
        try:
            if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                raise ValueError("Fecha inválida")
            observed_date = date.fromisoformat(day)
            if observed_date > today or (level is not None and (isinstance(level, bool) or not isinstance(level, (float, int)))):
                raise ValueError("Lectura inválida")
            readings.append(DailyLevel(observed_date=observed_date, level_m=level))
        except ValueError as exc:
            raise InvalidStationData("La serie contiene una lectura inválida.") from exc
    if len({item.observed_date for item in readings}) != len(readings):
        raise InvalidStationData("La serie contiene fechas duplicadas.")
    return sorted(readings, key=lambda item: item.observed_date)


class SenamhiProvider:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def get_public_document(self, url: str, accept: str = "text/html") -> bytes:
        # El timeout total también limita una respuesta que gotee indefinidamente.
        async with asyncio.timeout(20):
            async with httpx.AsyncClient(transport=self.transport, timeout=12, follow_redirects=False, headers={
                "User-Agent": "WAKI/0.1 (consulta de datos hidrologicos publicados)", "Accept": accept,
            }) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    if accept not in response.headers.get("content-type", ""):
                        raise InvalidStationData("Formato de respuesta inesperado.")
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 512 * 1024:
                            raise InvalidStationData("Respuesta demasiado grande.")
        return bytes(content)

    async def fetch(self, station: HydrologicalStation) -> list[DailyLevel]:
        content = await self.get_public_document(station.source_url)
        return parse_daily_levels(content.decode("utf-8"), station)
