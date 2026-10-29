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

    def get(self, report_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            return self._present(connection, row) if row else None

    def get_by_key(self, request_key: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM reports WHERE request_key=?", (request_key,)).fetchone()
            return self._present(connection, row) if row else None

    def list(self, limit: int, offset: int) -> tuple[list[dict], int]:
        with self.database.connect() as connection:
            connection.execute("BEGIN")
            total = connection.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM reports ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
            return [self._present(connection, row) for row in rows], total

    def get_photo(self, report_id: str, photo_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM report_photos WHERE report_id=? AND id=?", (report_id, photo_id)
            ).fetchone()
            return dict(row) if row else None

