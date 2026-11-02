# Conectar una cámara ESP32 a WAKI

El servidor recibe fotografías periódicas y el tablero muestra la última
recibida. No requiere que el ESP32 publique un servidor web ni un stream de video.
El firmware debe inicializar su módulo de cámara en formato JPEG y conectarse a WiFi.

## Cámaras registradas

| Río | `camera_id` |
| --- | --- |
| Chillón | `chillon-01` |
| Rímac | `rimac-01` |

El registro está en `app/services/cameras.py`. No se aceptan identificadores
arbitrarios ni un nombre de río enviado por el dispositivo.

## Clave y configuración

Define una clave privada `IOT_KEY` en `.env` y en el firmware. Puedes generar
una con `python -c 'import secrets; print(secrets.token_urlsafe(32))'` y guardarla
en ese archivo. No uses la clave en JavaScript del navegador ni la subas a Git.
La API permanece cerrada si la clave está vacía (HTTP 503).

```dotenv
IOT_KEY=tu_clave_privada
IOT_RETENTION_IMAGES=100
```

Con Docker, aplica la configuración mediante `docker compose up --build -d`.
La clave no se envía al navegador. La misma clave permite enviar a las cámaras
registradas; este alcance inicial no incluye credenciales distintas por dispositivo.

## Solicitud del ESP32

```http
POST /api/iot/upload?camera_id=chillon-01 HTTP/1.1
X-IoT-Key: tu_clave_privada
Content-Type: image/jpeg
Content-Length: tamaño_del_buffer

[bytes JPEG de fb->buf]
```

El cuerpo es el archivo binario completo: **sin JSON, base64 ni multipart**.
También se aceptan imágenes PNG y WebP declaradas con su tipo MIME. El servidor
comprueba el contenido real, aplica los límites de `MAX_UPLOAD_MB` y
`MAX_IMAGE_PIXELS`, corrige la orientación, elimina EXIF y normaliza a JPEG
con un lado máximo de `NORMALIZED_MAX_SIDE`.

`X-Captured-At` es opcional, en ISO 8601 con zona horaria, por ejemplo
`2026-10-29T12:00:00-05:00`. Solo envíalo cuando el reloj esté sincronizado.
Se rechazan fechas sin zona o adelantadas más de cinco minutos. Sin ese header,
la captura no tiene una hora de toma inventada: WAKI muestra su **hora de recepción**.
Las marcas se guardan en UTC y se muestran en hora de Lima.

Un HTTP **201** confirma que el JPEG y sus metadatos ya quedaron guardados:

```json
{
  "id": "uuid-generado-por-el-servidor",
  "camera_id": "chillon-01",
  "received_at": "fecha-UTC-de-recepcion",
  "captured_at": null,
  "width": 640,
  "height": 480,
  "size_bytes": 12345,
  "image_url": "/api/cameras/chillon-01/frames/uuid-generado-por-el-servidor/image"
}
```

Ese JSON es ilustrativo; los valores proceden del archivo real. HTTP 401 indica
clave incorrecta; 404 cámara desconocida; 413 exceso de tamaño o píxeles;
415 tipo de cuerpo no admitido; 422 archivo o fecha inválidos.
Cada solicitud aceptada crea una captura: los reenvíos de una misma foto no se
deduplican. La última recibida es la última guardada, aunque el reloj de captura
del dispositivo indique una fecha anterior.

## Probar desde una computadora

Con las dependencias del proyecto instaladas, el script lee la clave del entorno
o de `.env`, sin pasarla por argumentos de consola:

```bash
python scripts/send_iot.py /ruta/a/foto.jpg --camera chillon-01
python scripts/send_iot.py /ruta/a/foto.jpg --camera rimac-01 --url https://tu-dominio
```

## URL accesible desde el ESP32

`localhost` en el ESP32 identifica al propio dispositivo. Usa el dominio HTTPS
del servidor o su IP de la red local. Compose publica por defecto solo en
`127.0.0.1`, adecuado para acceso desde el servidor o mediante un proxy existente.
Para conectar por IP desde la misma red WiFi, puedes configurar explícitamente:

```dotenv
WAKI_BIND_ADDRESS=0.0.0.0
WAKI_PORT=8000
```

Recrea el servicio y utiliza `http://IP_DEL_SERVIDOR:8000/api/iot/upload?camera_id=chillon-01`.
Para un dominio HTTPS, configura la CA del servidor en el cliente TLS del ESP32.


## Panel y almacenamiento

- `GET /api/cameras/chillon-01/latest`: metadatos públicos; `latest: null` si no hay fotos.
- `GET /api/cameras/{camera_id}/frames/{id}/image`: JPEG público de una captura retenida.
- El navegador consulta cada **5 segundos**, al volver a la pestaña y al pulsar
  **Actualizar**. La fecha queda asociada a cada archivo; la antigüedad de recepción
  avanza sin cambiar la hora de la foto. Pasados dos minutos, se indica que es la
  última captura guardada, sin afirmar que la cámara sigue conectada.
- **Pantalla completa** utiliza la API del navegador y ofrece una vista ampliada
  cuando esa API no está disponible. Sin imágenes permanece desactivada.
- Las fotos son públicas en el tablero. Solo las subidas requieren la clave.
- La tabla `camera_frames` y `DATA_DIR/camera_photos/` son independientes de los
  reportes ciudadanos. Se conservan las últimas `IOT_RETENTION_IMAGES` fotos por
  cámara (100 por defecto); las anteriores se eliminan. El volumen Docker persiste
  ante reinicios. No hay segmentación ni análisis de IA en esta recepción.
- Al arrancar se limpian archivos IoT sin referencia tras guardados interrumpidos.
  Usa un solo proceso/worker, como el Compose incluido; no es un almacenamiento
  distribuido ni una cola de tareas.
