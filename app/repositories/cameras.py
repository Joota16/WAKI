from app.db.database import Database


class CamerasRepository:
    def __init__(self, database: Database):
        self.database = database

    def add(self, values: dict, retention: int) -> list[dict]:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""
                INSERT INTO camera_frames(id, camera_id, received_at, captured_at, filename, width, height, size_bytes)
                VALUES (:id, :camera_id, :received_at, :captured_at, :filename, :width, :height, :size_bytes)
            """, values)
            expired = connection.execute("""
                SELECT * FROM camera_frames WHERE camera_id=? ORDER BY sequence DESC LIMIT -1 OFFSET ?
            """, (values["camera_id"], retention)).fetchall()
            connection.executemany("DELETE FROM camera_frames WHERE id=?", [(row["id"],) for row in expired])
        return [dict(row) for row in expired]

    def latest(self, camera_id: str):
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM camera_frames WHERE camera_id=? ORDER BY sequence DESC LIMIT 1",
                                     (camera_id,)).fetchone()
        return dict(row) if row else None

    def get(self, camera_id: str, frame_id: str):
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM camera_frames WHERE camera_id=? AND id=?",
                                     (camera_id, frame_id)).fetchone()
        return dict(row) if row else None

    def filenames(self) -> set[str]:
        with self.database.connect() as connection:
            return {row["filename"] for row in connection.execute("SELECT filename FROM camera_frames")}
