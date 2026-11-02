import re
from typing import Annotated

from pydantic import BeforeValidator


def normalize_phone(value):
    if value is None or value == '':
        return None
    if not isinstance(value, str) or len(value) > 32:
        raise ValueError('Ingresa un celular de 9 dígitos que empiece con 9.')
    value = re.sub(r'[\s()\-]', '', value)
    if not value:
        return None
    if value.startswith('+51'):
        value = value[3:]
    elif value.startswith('51') and len(value) == 11:
        value = value[2:]
    if not re.fullmatch(r'9[0-9]{8}', value):
        raise ValueError('Ingresa un celular de 9 dígitos que empiece con 9.')
    return value


Phone = Annotated[str, BeforeValidator(normalize_phone)]
OptionalPhone = Annotated[str | None, BeforeValidator(normalize_phone)]
