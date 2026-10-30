from urllib.parse import urlsplit

from fastapi import Depends, Request

from app.services.auth import AuthContext, AuthError, COOKIE_NAME


def optional_session(request: Request) -> AuthContext | None:
    return request.app.state.auth.context(request.cookies.get(COOKIE_NAME))


def require_session(context: AuthContext | None = Depends(optional_session)) -> AuthContext:
    if context is None:
        raise AuthError('Inicia sesión para realizar esta acción.')
    return context


def require_admin(context: AuthContext = Depends(require_session)) -> AuthContext:
    if not context.is_admin:
        raise AuthError('Esta acción requiere una cuenta de administrador.', 403)
    return context


def session_write(request: Request, context: AuthContext = Depends(require_session)) -> AuthContext:
    same_origin(request)
    request.app.state.auth.verify_csrf(context, request.headers.get('x-csrf-token', ''))
    return context


def same_origin(request: Request):
    origin = request.headers.get('origin')
    if origin:
        try:
            parsed = urlsplit(origin)
        except ValueError as exc:
            raise AuthError('Origen de solicitud no permitido.', 403) from exc
        if parsed.scheme not in ('http', 'https') or parsed.netloc.casefold() != request.headers.get('host', '').casefold():
            raise AuthError('Origen de solicitud no permitido.', 403)


def admin_write(request: Request, context: AuthContext = Depends(require_admin)) -> AuthContext:
    same_origin(request)
    request.app.state.auth.verify_csrf(context, request.headers.get('x-csrf-token', ''))
    return context
