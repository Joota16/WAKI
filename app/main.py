import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import cameras, health, hydrology, iot, reports
from app.api.middleware import UploadBodyLimit
from app.config import Settings
from app.db.database import Database
from app.integrations.senamhi import SenamhiProvider
from app.integrations.senamhi_discharge import SenamhiDischargeProvider
from app.integrations.senamhi_weather import SenamhiWeatherProvider
from app.repositories.weather import WeatherRepository
from app.repositories.cameras import CamerasRepository
from app.repositories.discharge import DischargeRepository
from app.repositories.hydrology import HydrologyRepository
from app.repositories.reports import ReportsRepository
from app.services.images import ImagesService, ImageTooLarge, InvalidImage
from app.services.reports import DuplicateRequest, ReportNotFound, ReportsService
from app.services.hydrology import HydrologyService, LevelsProvider
from app.services.discharge import DischargeProvider, DischargeService
from app.services.weather import WeatherProvider, WeatherService
from app.services.cameras import CameraFrameNotFound, CameraNotFound, CamerasService
from app.web.pages import router as pages_router

STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None, *, hydrology_provider: LevelsProvider | None = None,
               discharge_provider: DischargeProvider | None = None, weather_provider: WeatherProvider | None = None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.database_path)
    images = ImagesService(settings)
    reports_service = ReportsService(ReportsRepository(database), images, settings)
    cameras_service = CamerasService(CamerasRepository(database), ImagesService(settings, settings.data_dir / "camera_photos"), settings)
    levels_service = HydrologyService(HydrologyRepository(database), hydrology_provider or SenamhiProvider(), settings)
    discharge_service = DischargeService(DischargeRepository(database), discharge_provider or SenamhiDischargeProvider(), settings)
    weather_service = WeatherService(WeatherRepository(database), weather_provider or SenamhiWeatherProvider(), settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database.initialize()
        images.initialize()
        cameras_service.initialize()
        tasks = [asyncio.create_task(service.run()) for service in (levels_service, discharge_service, weather_service)] if settings.senamhi_enabled else []
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
        description="Reportes ciudadanos con fotografías y ubicación. La IA no está implementada.",
        lifespan=lifespan,
    )
    application.state.database = database
    application.state.settings = settings
    application.state.reports = reports_service
    application.state.hydrology = levels_service
    application.state.discharge = discharge_service
    application.state.weather = weather_service
    application.state.cameras = cameras_service
    application.add_middleware(
        UploadBodyLimit, max_bytes=settings.upload_limit * settings.max_photos + 1024 * 1024,
    )

    @application.exception_handler(InvalidImage)
    async def invalid_image(request: Request, exc: InvalidImage):
        return JSONResponse({"detail": str(exc)}, status_code=413 if isinstance(exc, ImageTooLarge) else 422)

    @application.exception_handler(ReportNotFound)
    async def not_found(request: Request, exc: ReportNotFound):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @application.exception_handler(DuplicateRequest)
    async def duplicate_request(request: Request, exc: DuplicateRequest):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @application.exception_handler(CameraNotFound)
    @application.exception_handler(CameraFrameNotFound)
    async def camera_not_found(request: Request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    application.include_router(health.router)
    application.include_router(reports.router)
    application.include_router(hydrology.router)
    application.include_router(iot.router)
    application.include_router(cameras.router)
    application.include_router(pages_router)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return application


app = create_app()

