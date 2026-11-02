import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import alerts, analyses, attention, auth, cameras, health, hydrology, iot, reports, notifications
from fastapi.exceptions import RequestValidationError
from app.api.middleware import UploadBodyLimit
from app.config import Settings
from app.db.database import Database
from app.integrations.senamhi import SenamhiProvider
from app.integrations.senamhi_discharge import SenamhiDischargeProvider
from app.integrations.senamhi_weather import SenamhiWeatherProvider
from app.repositories.weather import WeatherRepository
from app.repositories.cameras import CamerasRepository
from app.repositories.analyses import AnalysesRepository
from app.repositories.discharge import DischargeRepository
from app.repositories.hydrology import HydrologyRepository
from app.repositories.reports import ReportsRepository
from app.repositories.users import UsersRepository
from app.repositories.alerts import AlertsRepository, InvalidAlertSource
from app.services.auth import AuthError, AuthService
from app.services.alerts import AlertNotFound, AlertsService
from app.services.attention import AttentionService
from app.services.images import ImagesService, ImageTooLarge, InvalidImage
from app.services.reports import DuplicateRequest, ReportNotFound, ReportsService
from app.services.hydrology import HydrologyService, LevelsProvider
from app.services.discharge import DischargeProvider, DischargeService
from app.services.weather import WeatherProvider, WeatherService
from app.services.cameras import CameraFrameNotFound, CameraNotFound, CamerasService
from app.services.processing import AnalysisBusy, AnalysisNotFound, ProcessingService
from app.services.notifications import NotificationsService
from app.vision.service import VisionProvider, build_provider
from app.web.pages import router as pages_router

STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None, *, hydrology_provider: LevelsProvider | None = None,
               discharge_provider: DischargeProvider | None = None, weather_provider: WeatherProvider | None = None,
               vision_provider: VisionProvider | None = None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.database_path)
    images = ImagesService(settings)
    auth_service = AuthService(UsersRepository(database), settings)
    alerts_service = AlertsService(AlertsRepository(database))
    reports_service = ReportsService(ReportsRepository(database), images, settings)
    attention_service = AttentionService(reports_service.repository)
    processing = ProcessingService(AnalysesRepository(database), vision_provider or build_provider(settings), settings)
    cameras_service = CamerasService(CamerasRepository(database), ImagesService(settings, settings.data_dir / "camera_photos"), settings, processing)
    levels_service = HydrologyService(HydrologyRepository(database), hydrology_provider or SenamhiProvider(), settings)
    discharge_service = DischargeService(DischargeRepository(database), discharge_provider or SenamhiDischargeProvider(), settings)
    weather_service = WeatherService(WeatherRepository(database), weather_provider or SenamhiWeatherProvider(), settings)
    notifications_service = NotificationsService(database, settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database.initialize()
        auth_service.initialize()
        notifications_service.initialize()
        images.initialize()
        cameras_service.initialize()
        processing.initialize()
        tasks = [asyncio.create_task(service.run()) for service in (levels_service, discharge_service, weather_service)] if settings.senamhi_enabled else []
        tasks.append(asyncio.create_task(notifications_service.run()))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError):
                    await task

    application = FastAPI(
        title=settings.app_name,
        version="0.0.1",
        description="Reportes ciudadanos, capturas IoT e informes de análisis visual configurables.",
        lifespan=lifespan,
    )
    application.state.database = database
    application.state.auth = auth_service
    application.state.alerts = alerts_service
    application.state.settings = settings
    application.state.reports = reports_service
    application.state.attention = attention_service
    application.state.hydrology = levels_service
    application.state.discharge = discharge_service
    application.state.weather = weather_service
    application.state.cameras = cameras_service
    application.state.processing = processing
    application.state.notifications = notifications_service
    application.add_middleware(
        UploadBodyLimit, max_bytes=settings.upload_limit * settings.max_photos + 1024 * 1024,
    )

    @application.exception_handler(AuthError)
    async def auth_error(request: Request, exc: AuthError):
        return JSONResponse({'detail': str(exc)}, status_code=exc.status, headers={'Cache-Control': 'no-store'})

    @application.exception_handler(AlertNotFound)
    async def alert_not_found(request: Request, exc: AlertNotFound):
        return JSONResponse({'detail': str(exc)}, status_code=404)

    @application.exception_handler(InvalidAlertSource)
    async def invalid_alert_source(request: Request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=422)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        errors = [{key: value for key, value in error.items() if key not in ('input', 'ctx')} for error in exc.errors()]
        return JSONResponse({'detail': errors}, status_code=422)

    @application.exception_handler(InvalidImage)
    async def invalid_image(request: Request, exc: InvalidImage):
        return JSONResponse({"detail": str(exc)}, status_code=413 if isinstance(exc, ImageTooLarge) else 422)

    @application.exception_handler(ReportNotFound)
    async def not_found(request: Request, exc: ReportNotFound):
        return JSONResponse({"detail": str(exc)}, status_code=404, headers={'Cache-Control': 'no-store'})

    @application.exception_handler(DuplicateRequest)
    async def duplicate_request(request: Request, exc: DuplicateRequest):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @application.exception_handler(CameraNotFound)
    @application.exception_handler(CameraFrameNotFound)
    async def camera_not_found(request: Request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @application.exception_handler(AnalysisNotFound)
    async def analysis_not_found(request: Request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=404)

    @application.exception_handler(AnalysisBusy)
    async def analysis_busy(request: Request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409)

    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(alerts.router)
    application.include_router(notifications.router)
    application.include_router(attention.router)
    application.include_router(reports.router)
    application.include_router(hydrology.router)
    application.include_router(iot.router)
    application.include_router(cameras.router)
    application.include_router(analyses.router)
    application.include_router(pages_router)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return application


app = create_app()

