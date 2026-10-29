from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import health, iot, reports
from app.config import Settings
from app.db.database import Database

STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.database_path)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database.initialize()
        yield

    application = FastAPI(
        title=settings.app_name,
        version="0.0.1",
        description="Estructura inicial de WAKI. Funcionalidades pendientes de implementación.",
        lifespan=lifespan,
    )
    application.state.database = database
    application.include_router(health.router)
    application.include_router(reports.router)
    application.include_router(iot.router)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return application


app = create_app()

