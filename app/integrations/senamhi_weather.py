"""Precipitación y temperaturas diarias del gráfico meteorológico público."""
from datetime import date, datetime
import json
import re
from zoneinfo import ZoneInfo

from app.integrations.senamhi import InvalidStationData, SenamhiProvider, _normalize, _variable
from app.schemas.weather import DailyWeather, WeatherStation

# El catálogo enlaza con 111159; la ficha publica Código: 156133. Ambos se verificaron.
OBRAJILLO_WEATHER = WeatherStation(
    code="156133", catalog_code="111159", name="Obrajillo", river_id="chillon",
    source_url="https://www.senamhi.gob.pe/mapas/mapa-estaciones-ms/map_red_graf.php?cod=111159",
)
WEATHER_STATIONS = {"chillon": OBRAJILLO_WEATHER}
SERIES = (
    ("Precipitación", "precipitation_mm", "mm"),
    ("Temp. max", "temperature_max_c", "°C"),
    ("Temp. min", "temperature_min_c", "°C"),
)


def parse_daily_weather(html: str, station: WeatherStation, today: date | None = None) -> list[DailyWeather]:
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script\s*>", html, flags=re.S | re.I)
    charts = [script for script in scripts if re.search(r"\bvar\s+categorias\s*=", script)]
    if len(charts) != 1:
        raise InvalidStationData("No se encontró el gráfico meteorológico público.")
    script = charts[0]
    title, subtitle = (_variable(script, name) for name in ("titulo", "subtitulo"))
    if (not isinstance(title, str) or not isinstance(subtitle, str)
            or _normalize(title).strip() != f"estacion: {_normalize(station.name)}"
            or "meteorologica" not in _normalize(subtitle)
            or not re.search(r"codigo:\s*" + re.escape(station.code) + r"\b", _normalize(subtitle))):
        raise InvalidStationData("La ficha no corresponde a la estación meteorológica esperada.")
    # Se comprueban las unidades de los ejes y de cada serie, sin ejecutar el gráfico.
    if "<b>Precipitación</b> (mm/día)" not in script or "<b>Temperatura</b> (°C)" not in script:
        raise InvalidStationData("Las unidades meteorológicas cambiaron.")
    dates = _variable(script, "categorias")
    if not isinstance(dates, list) or not 1 <= len(dates) <= 400:
        raise InvalidStationData("No hay fechas meteorológicas válidas.")
    declarations = list(re.finditer(r"^\s*name:\s*(['\"])(.*?)\1,\s*$", script, flags=re.M))
    if [item[2] for item in declarations] != [item[0] for item in SERIES]:
        raise InvalidStationData("La fuente cambió las series meteorológicas.")
    columns = {}
    for index, (_, key, unit) in enumerate(SERIES):
        block = script[declarations[index].end():declarations[index + 1].start() if index + 1 < len(declarations) else len(script)]
        assignments = list(re.finditer(r"^\s*data:\s*", block, flags=re.M))
        if len(assignments) != 1:
            raise InvalidStationData("Serie meteorológica ambigua.")
        try:
            raw = block[assignments[0].end():]
            values, end = json.JSONDecoder().raw_decode(raw)
            # Solo se acepta el array literal seguido por la unidad que usa el tooltip.
            suffix = re.match(r"\s*,\s*tooltip:\s*\{\s*valueSuffix:\s*(['\"])(.*?)\1\s*\}", raw[end:])
            if not suffix or suffix[2].strip() != unit or not isinstance(values, list) or len(values) != len(dates):
                raise ValueError("Serie incompatible")
        except (ValueError, TypeError) as exc:
            raise InvalidStationData("Serie meteorológica ilegible o unidad incorrecta.") from exc
        columns[key] = values
    today = today or datetime.now(ZoneInfo("America/Lima")).date()
    readings = []
    for index, day in enumerate(dates):
        try:
            if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                raise ValueError("Fecha inválida")
            observed_date = date.fromisoformat(day)
            if observed_date > today:
                raise ValueError("Fecha futura")
            values = {key: column[index] for key, column in columns.items()}
            if any(value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))) for value in values.values()):
                raise ValueError("Valor no numérico")
            readings.append(DailyWeather(observed_date=observed_date, **values))
        except ValueError as exc:
            raise InvalidStationData("La serie contiene una lectura meteorológica inválida.") from exc
    if len({item.observed_date for item in readings}) != len(readings):
        raise InvalidStationData("La serie meteorológica contiene fechas duplicadas.")
    return sorted(readings, key=lambda item: item.observed_date)


class SenamhiWeatherProvider(SenamhiProvider):
    async def fetch(self, station: WeatherStation) -> list[DailyWeather]:
        html = await self.get_public_document(station.source_url)
        return parse_daily_weather(html.decode("utf-8"), station)
