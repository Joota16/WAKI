from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import optional_session, same_origin, session_write
from app.schemas.auth import Credentials, PasswordChange, PhoneChange, Registration, SessionOut
from app.services.auth import AuthContext, COOKIE_NAME

router = APIRouter(prefix='/api/auth', tags=['Cuentas'])


def finish_login(request: Request, response: Response, user):
    token, context = request.app.state.auth.start_session(user)
    response.set_cookie(COOKIE_NAME, token, max_age=request.app.state.settings.jwt_expire_minutes * 60,
                        httponly=True, secure=request.app.state.settings.auth_cookie_secure,
                        samesite='lax', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.auth.session_out(context)


@router.post('/register', status_code=201, response_model=SessionOut, dependencies=[Depends(same_origin)])
def register(values: Registration, request: Request, response: Response):
    user = request.app.state.auth.register(values, request.client.host if request.client else 'unknown')
    return finish_login(request, response, user)


@router.post('/login', response_model=SessionOut, dependencies=[Depends(same_origin)])
def login(values: Credentials, request: Request, response: Response):
    user = request.app.state.auth.login(values, request.client.host if request.client else 'unknown')
    return finish_login(request, response, user)


@router.get('/me', response_model=SessionOut)
def me(request: Request, response: Response, context: AuthContext | None = Depends(optional_session)):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.auth.session_out(context)


@router.post('/logout', status_code=204, dependencies=[Depends(same_origin)])
def logout(request: Request, context: AuthContext | None = Depends(optional_session)):
    if context:
        request.app.state.auth.verify_csrf(context, request.headers.get('x-csrf-token', ''))
        request.app.state.auth.repository.revoke(context.session_id)
    return clear_session_cookie(request)


def clear_session_cookie(request: Request):
    response = Response(status_code=204, headers={'Cache-Control': 'no-store'})
    response.delete_cookie(COOKIE_NAME, path='/', httponly=True, samesite='lax', secure=request.app.state.settings.auth_cookie_secure)
    return response


@router.post('/password', status_code=204)
def change_password(values: PasswordChange, request: Request, context: AuthContext = Depends(session_write)):
    request.app.state.auth.change_password(context, values)
    return clear_session_cookie(request)


@router.put('/phone', response_model=SessionOut)
def change_phone(values: PhoneChange, request: Request, response: Response, context: AuthContext = Depends(session_write)):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.auth.change_phone(context, values.phone)
