import json

from app.db.database import Database


def check_connection(database: Database) -> bool:
    with database.connect() as connection:
        return connection.execute("SELECT 1").fetchone()[0] == 1


class ReportsRepository:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _present(connection, row) -> dict:
        result = dict(row)
        result["situations"] = json.loads(result.pop("situations_json"))
        result["photos"] = [dict(photo) for photo in connection.execute(
            "SELECT * FROM report_photos WHERE report_id=? ORDER BY rowid", (row["id"],)
        )]
        return result

    def create(self, row: dict, photos: list[dict]) -> None:
        columns = tuple(row)
        with self.database.connect() as connection:
            connection.execute(
                f"INSERT INTO reports ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                tuple(row.values()),
            )
            connection.executemany(
                "INSERT INTO report_photos (id,report_id,filename,width,height,size_bytes) VALUES (?,?,?,?,?,?)",
                [(photo["id"], row["id"], photo["filename"], photo["width"], photo["height"], photo["size_bytes"])
                 for photo in photos],
            )
            connection.execute("INSERT INTO public_events(event_type,payload_json,created_at) VALUES ('reports_changed','{}',?)", (row['created_at'],))

    def get(self, report_id: str, include_discarded: bool = False) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM reports WHERE id=? AND (review_status='validated' OR ?)", (report_id, include_discarded)).fetchone()
            return self._present(connection, row) if row else None

    def get_by_key(self, request_key: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM reports WHERE request_key=?", (request_key,)).fetchone()
            return self._present(connection, row) if row else None

    def list(self, limit: int, offset: int, include_discarded=False, review_status=None, admin=False) -> tuple[list[dict], int]:
        with self.database.connect() as connection:
            connection.execute("BEGIN")
            where = "(review_status='validated' OR ?) AND (review_status!='discarded' OR ?) AND (? IS NULL OR review_status=?)"
            params = (admin, include_discarded, review_status, review_status)
            total = connection.execute(f"SELECT COUNT(*) FROM reports WHERE {where}", params).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM reports WHERE {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?", (*params, limit, offset)
            ).fetchall()
            return [self._present(connection, row) for row in rows], total

    def get_photo(self, report_id: str, photo_id: str, include_discarded=False) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT p.* FROM report_photos p JOIN reports r ON r.id=p.report_id
                    WHERE p.report_id=? AND p.id=? AND (r.review_status='validated' OR ?)""", (report_id, photo_id, include_discarded)
            ).fetchone()
            return dict(row) if row else None

    def attention(self) -> dict | None:
        with self.database.connect() as db:
            row = db.execute("""SELECT id, attention_level, reviewed_at FROM reports
                WHERE review_status='validated' AND attention_level IS NOT NULL
                ORDER BY reviewed_at DESC, id DESC LIMIT 1""").fetchone()
        return dict(row) if row else None

    def review(self, report_id: str, actor_id: str, decision: str, notes: str, expected_version: int, now: str,
               attention_level: str | None = None):
        with self.database.connect() as db:
            changed = db.execute('''UPDATE reports SET review_status=?, review_notes=?, reviewed_at=?, reviewed_by=?,
                review_version=review_version+1, attention_level=? WHERE id=? AND review_version=?''',
                                 (decision, notes, now, actor_id, attention_level, report_id, expected_version)).rowcount
            if not changed:
                return False
            db.execute('INSERT INTO report_reviews(report_id,admin_id,decision,notes,created_at,attention_level) VALUES (?,?,?,?,?,?)',
                       (report_id, actor_id, decision, notes, now, attention_level))
            db.execute("INSERT INTO public_events(event_type,payload_json,created_at) VALUES ('reports_changed','{}',?)", (now,))
        return True

