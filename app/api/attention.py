from fastapi import APIRouter, Request, Response

from app.schemas.attention import AttentionSnapshot

router = APIRouter(prefix='/api/attention', tags=['Atención preventiva'])


@router.get('/chillon', response_model=AttentionSnapshot)
def current_attention(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.attention.snapshot()
