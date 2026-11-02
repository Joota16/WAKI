from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel

AnalysisStatus = Literal['queued', 'processing', 'analyzed', 'partial', 'not_configured', 'error']
STATUS_LABELS = {
    'queued': 'En cola', 'processing': 'Analizando', 'analyzed': 'Análisis terminado',
    'partial': 'Análisis parcial', 'not_configured': 'IA sin configurar', 'error': 'Error de análisis',
}


class AnalysisOut(BaseModel):
    id: UUID
    frame_id: UUID | None
    camera_id: str | None
    source: Literal['iot', 'test']
    source_label: str
    river_id: str
    received_at: AwareDatetime
    captured_at: AwareDatetime | None
    created_at: AwareDatetime
    completed_at: AwareDatetime | None
    status: AnalysisStatus
    status_label: str
    message: str
    water_fraction: float | None
    candidate_count: int | None
    objects_available: bool
    report_url: str
    original_url: str
    overlay_url: str | None
    artifacts: dict[str, str]
    result: dict | None = None


class AnalysisList(BaseModel):
    items: list[AnalysisOut]
    total: int
    limit: int
    offset: int
    poll_seconds: int = 5
