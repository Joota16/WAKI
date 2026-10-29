from fastapi import APIRouter, Request, Response

from app.schemas.hydrology import DischargeSnapshot, HydrologySnapshot, RiverId
from app.schemas.weather import WeatherSnapshot

router = APIRouter(prefix="/api/hydrology", tags=["Datos hidrometeorológicos"])


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
