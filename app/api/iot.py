"""Recepción autenticada de fotografías binarias de cámaras."""
import secrets
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import AwareDatetime, ValidationError
from starlette.concurrency import run_in_threadpool

from app.schemas.cameras import CameraFrame, CameraId, CameraUpload
from app.services.images import ImageTooLarge

router = APIRouter(prefix="/api/iot", tags=["Dispositivos"])


def require_iot_key(request: Request, x_iot_key: Annotated[str | None, Header()] = None):
    expected = request.app.state.settings.iot_key.get_secret_value()
    if not expected:
        raise HTTPException(status_code=503, detail="La recepción IoT no está configurada.")
    if not secrets.compare_digest(expected.encode(), (x_iot_key or "").encode()):
        raise HTTPException(status_code=401, detail="Clave IoT inválida.")


@router.post("/upload", status_code=201, response_model=CameraFrame, dependencies=[Depends(require_iot_key)],
             openapi_extra={"requestBody": {"required": True, "content": {
                 kind: {"schema": {"type": "string", "format": "binary"}}
                 for kind in ("image/jpeg", "image/png", "image/webp")
             }}})
async def upload(request: Request, background_tasks: BackgroundTasks, camera_id: CameraId,
                 x_captured_at: Annotated[AwareDatetime | None, Header()] = None):
    """Cuerpo: imagen binaria, sin multipart ni base64. Fecha de captura opcional."""
    try:
        metadata = CameraUpload(camera_id=camera_id, captured_at=x_captured_at)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_context=False, include_input=False)) from exc
    request.app.state.cameras.camera(camera_id)
    kind = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if kind not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Envía la imagen binaria con Content-Type image/jpeg, image/png o image/webp.")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > request.app.state.settings.upload_limit:
            raise ImageTooLarge("La captura supera el tamaño máximo permitido.")
        content.extend(chunk)
    frame = await run_in_threadpool(request.app.state.cameras.receive, metadata, bytes(content))
    background_tasks.add_task(request.app.state.processing.process, frame.id.hex)
    return frame

