from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.schemas.reports import ReportInput, ReportOut, ReportPage
from app.services.images import ImageTooLarge

router = APIRouter(prefix="/api/reports", tags=["Reportes"])


@router.post("", response_model=ReportOut, status_code=201)
async def create_report(request: Request, metadata: Annotated[str, Form(max_length=20_000)],
                        files: Annotated[list[UploadFile], File()],
                        idempotency_key: Annotated[UUID | None, Header()] = None):
    settings = request.app.state.settings
    try:
        try:
            values = ReportInput.model_validate_json(metadata)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors(include_context=False, include_input=False)) from exc
        if not 1 <= len(files) <= settings.max_photos:
            raise HTTPException(status_code=422, detail=f"Adjunta entre 1 y {settings.max_photos} fotografías.")
        contents = []
        for photo in files:
            content = await photo.read(settings.upload_limit + 1)
            if len(content) > settings.upload_limit:
                raise ImageTooLarge(f"Cada foto debe pesar como máximo {settings.max_upload_mb} MB.")
            contents.append(content)
        return await run_in_threadpool(request.app.state.reports.create, values, contents,
                                       str(idempotency_key) if idempotency_key else None)
    finally:
        for photo in files:
            await photo.close()


@router.get("", response_model=ReportPage)
def list_reports(request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 12,
                 offset: Annotated[int, Query(ge=0)] = 0):
    return request.app.state.reports.list(limit, offset)


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: UUID, request: Request):
    return request.app.state.reports.get(str(report_id))


@router.get("/{report_id}/photos/{photo_id}")
def get_photo(report_id: UUID, photo_id: UUID, request: Request):
    path = request.app.state.reports.photo_path(str(report_id), photo_id.hex)
    return FileResponse(path, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff"})

