from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse

from app.api.dependencies import same_origin
from app.schemas.notifications import NearbySubscription, SubscriptionToken

router = APIRouter(tags=['Avisos por cercanía'])
WORKER_FILE = Path(__file__).resolve().parent.parent / 'static' / 'js' / 'service-worker.js'


@router.get('/service-worker.js', include_in_schema=False)
def service_worker():
    return FileResponse(WORKER_FILE, media_type='text/javascript',
                        headers={'Cache-Control': 'no-cache', 'Service-Worker-Allowed': '/'})


@router.get('/api/notifications/config')
def config(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    service = request.app.state.notifications
    return {'enabled': bool(service.public_key), 'public_key': service.public_key,
            'location_max_age_seconds': service.settings.push_location_max_age_seconds}


def browser_write(request: Request):
    same_origin(request)
    if request.headers.get('x-waki-client') != 'browser':
        raise HTTPException(403, 'Solicitud de navegador no válida.')


@router.put('/api/notifications/subscription', dependencies=[Depends(browser_write)])
def subscribe(values: NearbySubscription, request: Request):
    service = request.app.state.notifications
    if not service.public_key:
        raise HTTPException(503, 'Las notificaciones están desactivadas.')
    try:
        location_at = service.subscribe(values)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {'location_at': location_at, 'expires_at': location_at + service.settings.push_location_max_age_seconds}


@router.delete('/api/notifications/subscription', status_code=204, dependencies=[Depends(browser_write)])
def unsubscribe(values: SubscriptionToken, request: Request):
    request.app.state.notifications.unsubscribe(values.token)
