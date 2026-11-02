from app.db.database import Database


class UsersRepository:
    def __init__(self, database: Database):
        self.database = database

    def by_username(self, key: str):
        with self.database.connect() as db:
            row = db.execute('SELECT * FROM users WHERE username_key=?', (key,)).fetchone()
        return dict(row) if row else None

    def create(self, values: dict):
        with self.database.connect() as db:
            db.execute('INSERT INTO users(id,username,username_key,password_hash,role,created_at) VALUES (:id,:username,:username_key,:password_hash,:role,:created_at)', values)

    def create_session(self, session_id: str, user_id: str, expires_at: int, now: int):
        with self.database.connect() as db:
            db.execute('DELETE FROM auth_sessions WHERE expires_at<=?', (now,))
            db.execute('INSERT INTO auth_sessions(id,user_id,expires_at) VALUES (?,?,?)', (session_id, user_id, expires_at))

    def session(self, session_id: str, user_id: str, now: int):
        with self.database.connect() as db:
            row = db.execute('''SELECT u.*, s.id AS session_id, s.expires_at FROM auth_sessions s
                JOIN users u ON u.id=s.user_id WHERE s.id=? AND u.id=? AND s.revoked=0 AND s.expires_at>?''',
                             (session_id, user_id, now)).fetchone()
        return dict(row) if row else None

    def revoke(self, session_id: str):
        with self.database.connect() as db:
            db.execute('UPDATE auth_sessions SET revoked=1 WHERE id=?', (session_id,))

    def change_password(self, user_id: str, session_id: str, previous_hash: str, new_hash: str, now: int):
        """Actualiza la clave y revoca todas las sesiones en una sola transacción."""
        with self.database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute('''UPDATE users SET password_hash=? WHERE id=? AND password_hash=?
                AND EXISTS (SELECT 1 FROM auth_sessions WHERE id=? AND user_id=? AND revoked=0 AND expires_at>?)''',
                (new_hash, user_id, previous_hash, session_id, user_id, now)).rowcount
            if changed:
                db.execute('UPDATE auth_sessions SET revoked=1 WHERE user_id=?', (user_id,))
            return bool(changed)

    def allow_attempt(self, bucket: str, now: int, limit: int = 30, window: int = 60) -> bool:
        with self.database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM auth_throttles WHERE window_start<=?', (now - window,))
            db.execute('''INSERT INTO auth_throttles(bucket,window_start,attempts) VALUES (?,?,1)
                ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1''', (bucket, now))
            return db.execute('SELECT attempts FROM auth_throttles WHERE bucket=?', (bucket,)).fetchone()[0] <= limit
