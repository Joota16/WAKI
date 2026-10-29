from pathlib import Path
import sqlite3
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.integrations.senamhi_discharge import DISCHARGE_STATIONS
from app.integrations.senamhi_weather import OBRAJILLO_WEATHER
from app.services.cameras import CAMERAS

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")
router = APIRouter(include_in_schema=False)
templates.env.filters["lima_datetime"] = lambda value: value.astimezone(ZoneInfo("America/Lima")).strftime("%d/%m/%Y %H:%M")


@router.get("/", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard/index.html",
                                      context={"discharge_stations": DISCHARGE_STATIONS, "weather_station": OBRAJILLO_WEATHER,
                                               "camera_ids": {item.river_id: item.id for item in CAMERAS.values()}})


@router.get("/reportar", response_class=HTMLResponse, name="citizen_report")
def citizen_report(request: Request):
    settings = request.app.state.settings
    return templates.TemplateResponse(request=request, name="citizen/index.html", context={
        "limits": {"max_photos": settings.max_photos, "max_upload_mb": settings.max_upload_mb,
                   "max_image_pixels": settings.max_image_pixels},
    })


@router.get("/reportes", response_class=HTMLResponse, name="reports_list")
def reports_list(request: Request, page: Annotated[int, Query(ge=1, le=1_000_000)] = 1):
    limit = 12
    try:
        result = request.app.state.reports.list(limit, (page - 1) * limit)
    except sqlite3.Error:
        return templates.TemplateResponse(request=request, name="reports/list.html", status_code=503,
                                          context={"error": True, "reports": [], "total": 0})
    pages = max(1, (result.total + limit - 1) // limit)
    if page > pages:
        return RedirectResponse(request.url_for("reports_list").include_query_params(page=pages), status_code=303)
    return templates.TemplateResponse(request=request, name="reports/list.html", context={
        "reports": result.items, "total": result.total, "page": page, "pages": pages,
        "start": result.offset + 1 if result.total else 0,
        "end": result.offset + len(result.items), "error": False,
    })


@router.get("/reportes/{report_id}", response_class=HTMLResponse, name="report_detail")
def report_detail(report_id: UUID, request: Request):
    report = request.app.state.reports.get(str(report_id))
    return templates.TemplateResponse(request=request, name="reports/detail.html", context={
        "report": report,
        "registered_local": report.created_at.astimezone(ZoneInfo("America/Lima")).strftime("%d/%m/%Y a las %H:%M"),
    })

