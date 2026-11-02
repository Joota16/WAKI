from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class UploadBodyLimit:
    """Acota las solicitudes antes de procesar multipart, con y sin Content-Length."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None:
            try:
                size = int(length)
                if size < 0:
                    raise ValueError
            except ValueError:
                return await JSONResponse({"detail": "Content-Length inválido."}, status_code=400)(scope, receive, send)
            if size > self.max_bytes:
                return await JSONResponse({"detail": "La solicitud supera el tamaño permitido."}, status_code=413)(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(status_code=413, detail="La solicitud supera el tamaño permitido.")
            return message

        return await self.app(scope, limited_receive, send)
