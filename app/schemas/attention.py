from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel

AttentionLevel = Literal['monitoring', 'preventive', 'priority']
ATTENTION_LABELS = {
    'monitoring': 'Seguimiento',
    'preventive': 'Atención preventiva',
    'priority': 'Atención prioritaria',
}


class AttentionSnapshot(BaseModel):
    river_id: Literal['chillon'] = 'chillon'
    level: AttentionLevel | None = None
    label: str = 'Pendiente de evaluación'
    evaluated_at: AwareDatetime | None = None
    source_report_id: UUID | None = None
    source_report_url: str | None = None
