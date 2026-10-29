from uuid import UUID

from fastapi import APIRouter, Request, Response

from app.schemas.cameras import CameraId, LatestCameraFrame

router = APIRouter(prefix="/api/cameras", tags=["Cámaras"])


@router.get("/{camera_id}/latest", response_model=LatestCameraFrame)
def latest(camera_id: CameraId, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.cameras.latest(camera_id)


@router.get("/{camera_id}/frames/{frame_id}/image")
def image(camera_id: CameraId, frame_id: UUID, request: Request):
    content = request.app.state.cameras.image(camera_id, frame_id)
    return Response(content=content, media_type="image/jpeg", headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=86400, immutable",
        "ETag": f'"{frame_id}"',
    })
