import base64
from urllib.parse import urlsplit
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SubscriptionKeys(BaseModel):
    model_config = ConfigDict(extra='forbid')
    p256dh: str = Field(max_length=100)
    auth: str = Field(max_length=30)

    @field_validator('p256dh', 'auth')
    @classmethod
    def valid_key(cls, value, info):
        try:
            decoded = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
            if info.field_name == 'p256dh':
                ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), decoded)
            elif len(decoded) != 16:
                raise ValueError()
        except (ValueError, TypeError) as exc:
            raise ValueError('Clave de notificaciones inválida.') from exc
        return value


class PushSubscription(BaseModel):
    model_config = ConfigDict(extra='ignore')  # El navegador puede incluir expirationTime.
    endpoint: str = Field(min_length=20, max_length=2048)
    keys: SubscriptionKeys

    @field_validator('endpoint')
    @classmethod
    def trusted_push_service(cls, value):
        parsed = urlsplit(value)
        host = parsed.hostname or ''
        trusted = host in ('fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com') or any(
            host.endswith('.' + domain) for domain in ('push.services.mozilla.com', 'notify.windows.com', 'web.push.apple.com'))
        if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.fragment or not trusted or not parsed.path.strip('/')):
            raise ValueError('El destino no es un servicio de notificaciones compatible.')
        return value


class SubscriptionToken(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: UUID


class NearbySubscription(SubscriptionToken):
    subscription: PushSubscription
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    accuracy_m: float = Field(gt=0, le=1000, allow_inf_nan=False)
