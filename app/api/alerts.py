import asyncio
import json
from typing import Annotated
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import admin_write, require_admin
from app.schemas.alerts import AlertHistoryPage, AlertInput, AlertOut, AlertsSnapshot, GuidedAlertInput, MonitoringPointInput
from app.services.auth import AuthContext

router = APIRouter(prefix='/api', tags=['Avisos importantes'])


@router.get('/alerts', response_model=AlertsSnapshot)
def alerts(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.alerts.snapshot()


@router.post('/alerts', status_code=201, response_model=AlertOut)
def create(values: GuidedAlertInput | AlertInput, request: Request, context: AuthContext = Depends(admin_write)):
    return request.app.state.alerts.create(values, str(context.user.id))


@router.get('/admin/alerts/options')
def alert_options(request: Request, response: Response, limit: Annotated[int, Query(ge=1, le=50)] = 25,
                  offset: Annotated[int, Query(ge=0)] = 0, context: AuthContext = Depends(require_admin)):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.alerts.options(limit, offset)


@router.put('/admin/alerts/points/{camera_id}')
def save_point(camera_id: str, values: MonitoringPointInput, request: Request, context: AuthContext = Depends(admin_write)):
    return request.app.state.alerts.save_point(camera_id, values, str(context.user.id))


@router.get('/admin/alerts/history', response_model=AlertHistoryPage)
def alert_history(request: Request, response: Response, limit: Annotated[int, Query(ge=1, le=50)] = 10,
                  offset: Annotated[int, Query(ge=0)] = 0, status: Literal['all', 'active', 'closed'] = 'all',
                  context: AuthContext = Depends(require_admin)):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.alerts.history(limit, offset, status)


@router.post('/alerts/{alert_id}/close', response_model=AlertOut)
def close(alert_id: UUID, request: Request, context: AuthContext = Depends(admin_write)):
    return request.app.state.alerts.close(str(alert_id), str(context.user.id))


@router.get('/events')
async def events(request: Request, after: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
                 last_event_id: Annotated[str | None, Header()] = None):
    if last_event_id and last_event_id.isdigit() and len(last_event_id) < 20:
        after = max(after, min(int(last_event_id), 9223372036854775807))

    async def stream():
        cursor = after
        idle = 0
        yield 'retry: 3000\n: connected\n\n'
        while not await request.is_disconnected():
            updates = await run_in_threadpool(request.app.state.alerts.events, cursor)
            for event in updates:
                cursor = event['id']
                yield f"id: {cursor}\nevent: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
            idle += 1
            if idle >= 15:
                yield ': heartbeat\n\n'
                idle = 0
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no'})
