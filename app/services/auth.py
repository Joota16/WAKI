from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import time
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.config import Settings
from app.repositories.users import UsersRepository
from app.schemas.auth import Credentials, PasswordChange, Registration, SessionOut, UserOut

COOKIE_NAME = 'waki_access'


class AuthError(ValueError):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class AuthContext:
    user: UserOut
    session_id: str
    expires_at: int

    @property
    def is_admin(self):
        return self.user.role == 'admin'


class AuthService:
    def __init__(self, repository: UsersRepository, settings: Settings):
        self.repository, self.settings = repository, settings
        self.passwords = PasswordHash.recommended()
        self.secret = ''
        self.dummy_hash = None

    def initialize(self):
        self.secret = self.settings.jwt_secret.get_secret_value()
        if not self.secret:
            path = self.settings.data_dir / '.jwt-secret'
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                self.secret = path.read_text().strip()
            else:
                self.secret = secrets.token_urlsafe(48)
                with os.fdopen(descriptor, 'w') as output:
                    output.write(self.secret)
            if len(self.secret) < 32:
                raise ValueError('La clave JWT persistida no es válida.')
        if self.settings.admin_username and self.settings.admin_password.get_secret_value():
            credentials = Credentials(username=self.settings.admin_username, password=self.settings.admin_password)
            existing = self.repository.by_username(credentials.username.casefold())
            if existing is None:
                self._create_user(credentials, 'admin')
            elif existing['role'] != 'admin':
                logging.getLogger(__name__).error('ADMIN_USERNAME ya pertenece a un usuario normal; no se modificó su rol.')

    def _create_user(self, credentials: Credentials, role: str):
        values = {'id': str(uuid4()), 'username': credentials.username, 'username_key': credentials.username.casefold(),
                  'password_hash': self.passwords.hash(credentials.password.get_secret_value()), 'role': role,
                  'created_at': datetime.now(timezone.utc).isoformat()}
        try:
            self.repository.create(values)
        except sqlite3.IntegrityError as exc:
            raise AuthError('Ese nombre de usuario ya está registrado.', 409) from exc
        return UserOut(**values)

    def throttle(self, client: str, action: str):
        bucket = hmac.new(self.secret.encode(), f'{action}:{client}'.encode(), hashlib.sha256).hexdigest()
        if not self.repository.allow_attempt(bucket, int(time.time())):
            raise AuthError('Demasiados intentos. Espera un minuto y vuelve a intentarlo.', 429)

    def register(self, values: Registration, client: str):
        self.throttle(client, 'register')
        return self._create_user(values, 'user')

    def login(self, values: Credentials, client: str):
        self.throttle(client, 'login')
        row = self.repository.by_username(values.username.casefold())
        if self.dummy_hash is None:
            self.dummy_hash = self.passwords.hash(secrets.token_urlsafe(32))
        valid = self.passwords.verify(values.password.get_secret_value(), row['password_hash'] if row else self.dummy_hash)
        if row is None or not valid:
            raise AuthError('Usuario o contraseña incorrectos.')
        return UserOut(**row)

    def start_session(self, user: UserOut):
        now = int(time.time())
        expires = now + self.settings.jwt_expire_minutes * 60
        session_id = uuid4().hex
        self.repository.create_session(session_id, str(user.id), expires, now)
        token = jwt.encode({'sub': str(user.id), 'jti': session_id, 'iat': now, 'nbf': now, 'exp': expires,
                            'iss': 'waki', 'aud': 'waki-web'}, self.secret, algorithm='HS256')
        return token, AuthContext(user, session_id, expires)

    def context(self, token: str | None):
        if not token or len(token) > 4096:
            return None
        try:
            claims = jwt.decode(token, self.secret, algorithms=['HS256'], audience='waki-web', issuer='waki',
                                options={'require': ['sub', 'jti', 'iat', 'nbf', 'exp']})
            if not isinstance(claims['sub'], str) or not isinstance(claims['jti'], str):
                return None
            row = self.repository.session(claims['jti'], claims['sub'], int(time.time()))
            return AuthContext(UserOut(**row), row['session_id'], row['expires_at']) if row else None
        except jwt.InvalidTokenError:
            return None

    def csrf(self, context: AuthContext):
        return hmac.new(self.secret.encode(), f'csrf:{context.session_id}'.encode(), hashlib.sha256).hexdigest()

    def change_password(self, context: AuthContext, values: PasswordChange):
        self.throttle(str(context.user.id), 'password-change')
        row = self.repository.by_username(context.user.username.casefold())
        if row is None or not self.passwords.verify(values.current_password.get_secret_value(), row['password_hash']):
            raise AuthError('La contraseña actual es incorrecta.', 400)
        new_hash = self.passwords.hash(values.new_password.get_secret_value())
        if not self.repository.change_password(str(context.user.id), context.session_id,
                                               row['password_hash'], new_hash, int(time.time())):
            raise AuthError('La cuenta cambió durante la solicitud. Inicia sesión de nuevo.', 409)

    def session_out(self, context: AuthContext | None):
        return SessionOut(user=context.user, csrf_token=self.csrf(context),
                          expires_at=datetime.fromtimestamp(context.expires_at, timezone.utc)) if context else SessionOut()

    def verify_csrf(self, context: AuthContext, value: str):
        if not secrets.compare_digest(self.csrf(context).encode(), value.encode()):
            raise AuthError('La sesión de seguridad no es válida. Recarga la página.', 403)
