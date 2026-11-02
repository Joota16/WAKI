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
from app.api.dependencies import optional_session

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")
router = APIRouter(include_in_schema=False)
templates.env.filters["lima_datetime"] = lambda value: value.astimezone(ZoneInfo("America/Lima")).strftime("%d/%m/%Y %H:%M")

ACCOUNT_DESTINATIONS = {'/', '/administrar', '/admin/avisos', '/admin/reportes'}


def access_page(request: Request, mode: str, destination: str = '/'):
    destination = destination if destination in ACCOUNT_DESTINATIONS else '/'
    session = optional_session(request)
    if session:
        target = destination if session.is_admin or not destination.startswith('/admin/') else '/'
        return RedirectResponse(target, status_code=303, headers={'Cache-Control': 'no-store'})
    return templates.TemplateResponse(request=request, name='account/access.html',
                                      context={'mode': mode, 'destination': destination},
                                      headers={'Cache-Control': 'no-store'})


@router.get('/ingresar', response_class=HTMLResponse, name='login_page')
def login_page(request: Request, next: str = '/'):
    return access_page(request, 'login', next)


@router.get('/registro', response_class=HTMLResponse, name='register_page')
def register_page(request: Request, next: str = '/'):
    return access_page(request, 'register', next)


def protected_page(request: Request, template: str, admin: bool = False, context: dict | None = None):
    session = optional_session(request)
    if not session:
        return RedirectResponse(request.url_for('login_page').replace(query='').include_query_params(next=request.url.path),
                                status_code=303, headers={'Cache-Control': 'no-store'})
    if admin and not session.is_admin:
        return templates.TemplateResponse(request=request, name='account/forbidden.html', status_code=403,
                                          headers={'Cache-Control': 'no-store'})
    return templates.TemplateResponse(request=request, name=template, context=context or {},
                                      headers={'Cache-Control': 'no-store'})


@router.get('/administrar', response_class=HTMLResponse, name='account_settings')
def account_settings(request: Request):
    return protected_page(request, 'account/settings.html')


@router.get('/admin/avisos', response_class=HTMLResponse, name='admin_alerts')
def admin_alerts(request: Request):
    return protected_page(request, 'admin/alerts.html', admin=True)


@router.get('/admin/reportes', response_class=HTMLResponse, name='admin_reports')
def admin_reports(request: Request, report_id: UUID | None = None):
    return protected_page(request, 'admin/reports.html', admin=True,
                          context={'report_id': str(report_id) if report_id else ''})


@router.get("/", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard/index.html",
                                      context={"discharge_stations": DISCHARGE_STATIONS, "weather_station": OBRAJILLO_WEATHER,
                                               "camera_capture_seconds": request.app.state.settings.camera_capture_seconds,
                                               "upload_limit_mb": request.app.state.settings.max_upload_mb,
                                               "camera_ids": {item.river_id: item.id for item in CAMERAS.values()
                                                              if item.river_id == 'chillon'}})


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
    }, headers={'Cache-Control': 'no-store'})


@router.get("/reportes/{report_id}", response_class=HTMLResponse, name="report_detail")
def report_detail(report_id: UUID, request: Request):
    session = optional_session(request)
    report = request.app.state.reports.get(str(report_id), admin=bool(session and session.is_admin))
    return templates.TemplateResponse(request=request, name="reports/detail.html", context={
        "report": report,
        "registered_local": report.created_at.astimezone(ZoneInfo("America/Lima")).strftime("%d/%m/%Y a las %H:%M"),
    }, headers={'Cache-Control': 'no-store'})


@router.get('/informes-ia/{analysis_id}', response_class=HTMLResponse, name='analysis_detail')
def analysis_detail(analysis_id: UUID, request: Request):
    analysis = request.app.state.processing.get(analysis_id)
    return templates.TemplateResponse(request=request, name='analyses/detail.html', context={'analysis': analysis})


@router.get('/informes-ia/{analysis_id}/contenido', response_class=HTMLResponse, name='analysis_content')
def analysis_content(analysis_id: UUID, request: Request):
    analysis = request.app.state.processing.get(analysis_id)
    return templates.TemplateResponse(request=request, name='analyses/content.html',
                                      context={'analysis': analysis, 'embedded': True},
                                      headers={'Cache-Control': 'no-store'})

