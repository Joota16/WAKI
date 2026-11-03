from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.schemas.hydrology import DischargeSnapshot, HydrologySnapshot, RiverId
from app.schemas.weather import WeatherSnapshot
from app.services.monitoring_history import MonitoringHistory

router = APIRouter(prefix="/api/hydrology", tags=["Datos hidrometeorológicos"])


@router.get('/{river_id}/history/{metric}')
def get_history(river_id: RiverId, metric: Literal['level', 'discharge', 'weather'], request: Request, response: Response,
                station_code: Annotated[str | None, Query(max_length=32)] = None,
                limit: Annotated[int, Query(ge=1, le=100)] = 25,
                offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0):
    response.headers['Cache-Control'] = 'no-store'
    page = MonitoringHistory(request.app.state.database).get(river_id, metric, station_code, limit, offset)
    if page is None:
        raise HTTPException(404, 'No se encontró la estación para este historial.')
    return page


@router.get("/{river_id}/weather", response_model=WeatherSnapshot)
def get_weather(river_id: RiverId, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.weather.get(river_id)


@router.get("/{river_id}/discharge", response_model=list[DischargeSnapshot])
def get_discharge(river_id: RiverId, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.discharge.get(river_id)


@router.get("/{river_id}", response_model=HydrologySnapshot)
def get_levels(river_id: RiverId, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.hydrology.get(river_id)
