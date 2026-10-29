"""Envía una foto binaria como lo hará el ESP32, leyendo IOT_KEY del entorno/.env."""
import argparse
import json
import mimetypes
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from dotenv import dotenv_values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--url', default='http://127.0.0.1:8000', help='URL base de WAKI')
    parser.add_argument('--camera', default='chillon-01')
    parser.add_argument('--captured-at', help='Fecha ISO 8601 con zona horaria; opcional')
    args = parser.parse_args()
    key = os.environ.get('IOT_KEY') or dotenv_values(Path(__file__).resolve().parent.parent / '.env').get('IOT_KEY')
    if not key:
        parser.error('Configura IOT_KEY en el entorno o en .env.')
    kind = mimetypes.guess_type(args.image.name)[0]
    if kind not in {'image/jpeg', 'image/png', 'image/webp'}:
        parser.error('Selecciona un archivo JPEG, PNG o WebP.')
    headers = {'X-IoT-Key': key, 'Content-Type': kind}
    if args.captured_at:
        headers['X-Captured-At'] = args.captured_at
    try:
        url = args.url.rstrip('/') + '/api/iot/upload?' + urlencode({'camera_id': args.camera})
        request = Request(url, data=args.image.read_bytes(), headers=headers, method='POST')
        with urlopen(request, timeout=30) as response:
            print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
        return 0
    except HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}", file=sys.stderr)
    except (OSError, URLError, ValueError) as exc:
        print(f'No se pudo enviar la captura: {exc}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
