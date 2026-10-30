from app.repositories.reports import ReportsRepository
from app.schemas.attention import ATTENTION_LABELS, AttentionSnapshot


class AttentionService:
    def __init__(self, repository: ReportsRepository):
        self.repository = repository

    def snapshot(self) -> AttentionSnapshot:
        row = self.repository.attention()
        if row is None:
            return AttentionSnapshot()
        return AttentionSnapshot(level=row['attention_level'], label=ATTENTION_LABELS[row['attention_level']],
                                 evaluated_at=row['reviewed_at'], source_report_id=row['id'],
                                 source_report_url=f"/reportes/{row['id']}")
