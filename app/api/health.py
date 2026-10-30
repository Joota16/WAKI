import sqlite3

from fastapi import APIRouter, Request, Response

from app.repositories.reports import check_connection

router = APIRouter(prefix="/api", tags=["Estado"])


@router.get("/health")
def health(request: Request, response: Response):
    try:
        connected = check_connection(request.app.state.database)
    except sqlite3.Error:
        connected = False
    if not connected:
        response.status_code = 503
    return {
        "status": "ok" if connected else "error",
        "database": "connected" if connected else "unavailable",
        "vision": {"provider": request.app.state.settings.model_provider,
                   "device": request.app.state.settings.ai_device,
                   "objects_configured": bool(request.app.state.settings.ai_dino_checkpoint or request.app.state.settings.ai_yoloe_checkpoint)},
    }

