from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.api.iot import require_iot_key
from app.schemas.analyses import AnalysisList, AnalysisOut
from app.schemas.cameras import CameraId
from app.schemas.hydrology import RiverId

router = APIRouter(prefix='/api', tags=['Informes de IA'])


@router.post('/analysis-tests', response_model=AnalysisOut, status_code=202,
             dependencies=[Depends(require_iot_key)])
async def create_test(request: Request, background_tasks: BackgroundTasks, river_id: RiverId,
                      file: Annotated[UploadFile, File()]):
    """Prueba manual autenticada; no registra una captura IoT ni un reporte ciudadano."""
    try:
        content = await file.read(request.app.state.settings.upload_limit + 1)
    finally:
        await file.close()
    result = await run_in_threadpool(request.app.state.processing.create_test, river_id, content)
    background_tasks.add_task(request.app.state.processing.process, result.id.hex)
    return result


@router.get('/analysis-tests', response_model=AnalysisList)
def list_tests(request: Request, response: Response, river_id: RiverId,
               limit: Annotated[int, Query(ge=1, le=50)] = 6,
               offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.processing.list_tests(river_id, limit, offset)


@router.get('/cameras/{camera_id}/analyses', response_model=AnalysisList)
def analyses(camera_id: CameraId, request: Request, response: Response,
             limit: Annotated[int, Query(ge=1, le=50)] = 6,
             offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0):
    request.app.state.cameras.camera(camera_id)
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.processing.list(camera_id, limit, offset)


@router.get('/analyses/{analysis_id}', response_model=AnalysisOut)
def analysis(analysis_id: UUID, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.processing.get(analysis_id)


@router.get('/analyses/{analysis_id}/report.json')
def download_report(analysis_id: UUID, request: Request):
    result = request.app.state.processing.get(analysis_id)
    return JSONResponse(result.model_dump(mode='json'), headers={
        'Content-Disposition': f'attachment; filename="waki-ia-{analysis_id}.json"',
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })


@router.get('/analyses/{analysis_id}/artifacts/{kind}')
def artifact(analysis_id: UUID, kind: str, request: Request):
    content, media_type = request.app.state.processing.artifact(analysis_id, kind)
    return Response(content, media_type=media_type,
                    headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.post('/analyses/{analysis_id}/retry', response_model=AnalysisOut, status_code=202,
             dependencies=[Depends(require_iot_key)])
def retry(analysis_id: UUID, request: Request, background_tasks: BackgroundTasks):
    result = request.app.state.processing.retry(analysis_id)
    background_tasks.add_task(request.app.state.processing.process, analysis_id.hex)
    return result
