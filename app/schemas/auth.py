from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=3, max_length=32, pattern=r'^[A-Za-z0-9_.-]+$')
    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator('username', mode='before')
    @classmethod
    def trim_username(cls, value):
        return value.strip() if isinstance(value, str) else value


class Registration(Credentials):
    password_confirmation: SecretStr = Field(min_length=8, max_length=128)

    @model_validator(mode='after')
    def matching_passwords(self):
        if self.password.get_secret_value() != self.password_confirmation.get_secret_value():
            raise ValueError('Las contraseñas no coinciden.')
        return self


class UserOut(BaseModel):
    id: UUID
    username: str
    role: Literal['user', 'admin']


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current_password: SecretStr = Field(min_length=8, max_length=128)
    new_password: SecretStr = Field(min_length=8, max_length=128)
    password_confirmation: SecretStr = Field(min_length=8, max_length=128)

    @model_validator(mode='after')
    def matching_passwords(self):
        if self.new_password.get_secret_value() != self.password_confirmation.get_secret_value():
            raise ValueError('Las contraseñas nuevas no coinciden.')
        if self.new_password.get_secret_value() == self.current_password.get_secret_value():
            raise ValueError('Elige una contraseña diferente de la actual.')
        return self


class SessionOut(BaseModel):
    user: UserOut | None = None
    csrf_token: str | None = None
    expires_at: datetime | None = None
