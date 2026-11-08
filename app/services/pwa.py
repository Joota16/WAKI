"""Recursos públicos del formulario; las respuestas de API y cuentas no se cachean."""
from functools import lru_cache
import hashlib
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = APP_DIR / 'static'


@lru_cache(maxsize=1)
def offline_resources() -> tuple[tuple[str, ...], str]:
    assets = sorted(path for path in STATIC_DIR.rglob('*') if path.is_file() and (
        path.suffix in ('.js', '.css', '.woff2')
        or path == STATIC_DIR / 'manifest.webmanifest'
        or path == STATIC_DIR / 'offline.html'
        or path == STATIC_DIR / 'img' / 'waki-logo.png'
        or path.parent == STATIC_DIR / 'img' / 'icons'))
    digest = hashlib.sha256()
    for path in [*assets, *sorted((APP_DIR / 'templates').rglob('*.html'))]:
        digest.update(path.relative_to(APP_DIR).as_posix().encode())
        digest.update(path.read_bytes())
    return tuple('/static/' + path.relative_to(STATIC_DIR).as_posix() for path in assets), digest.hexdigest()[:16]
