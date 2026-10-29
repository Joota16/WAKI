# WAKI

Arquitectura modular para monitoreo visual de ríos.

## Alcance actual

Este repositorio contiene únicamente la arquitectura inicial y la conexión
básica de FastAPI con SQLite. No hay tablas de reportes, carga de fotografías,
autenticación, revisiones, procesamiento ni IA implementados.

Los módulos vacíos marcan dónde se desarrollará cada responsabilidad. La página
inicial es un marcador de posición, no la interfaz del MVP.

## Estructura

```text
app/
├── __init__.py
├── main.py                  # Inicializa FastAPI y registra las rutas
├── config.py                # Variables de entorno
├── api/
│   ├── health.py            # Comprobación de conexión SQLite
│   ├── reports.py           # Router reservado
│   └── iot.py               # Router reservado
├── schemas/
│   └── reports.py           # Contratos futuros de entrada y salida
├── services/
│   ├── reports.py           # Casos de uso futuros
│   ├── processing.py        # Coordinación futura de tareas
│   └── images.py            # Manejo futuro de imágenes
├── repositories/
│   └── reports.py           # Consultas SQL y comprobación de conexión
├── db/
│   └── database.py          # Conexiones y creación del archivo SQLite
├── vision/
│   ├── service.py           # Reservado, sin implementación
│   └── providers/
│       └── yolo.py          # Reservado, sin implementación
└── static/
    ├── index.html           # Página inicial mínima
    ├── styles.css
    └── app.js
tests/                      # Reservado
scripts/                    # Reservado
.env.example
.gitignore
requirements.txt
requirements-ai.txt         # Reservado; no instala dependencias
```

Los paquetes Python incluyen sus archivos `__init__.py`.

## Responsabilidades y dependencias

- `main.py` ensambla la aplicación.
- `api/` gestiona HTTP y utilizará los servicios para las operaciones de negocio.
- `schemas/` definirá los contratos de entrada y salida.
- `services/` coordinará casos de uso sin depender de `Request` ni `Response`.
- `repositories/` concentra SQL y utiliza `db/` para conectarse.
- `db/` administra conexiones y, más adelante, el esquema.
- `vision/` queda reservado para encapsular proveedores futuros.
- `static/` alojará la interfaz sin frameworks.

Flujo previsto: `api → services → repositories → db`. Los servicios podrán
utilizar el módulo de visión cuando esa etapa se autorice.

## Instalación y ejecución

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

Abrir http://127.0.0.1:8000 y la documentación en http://127.0.0.1:8000/docs.
Al iniciar se crea `data/waki.sqlite3`, todavía sin tablas de negocio.
`DATA_DIR` permite cambiar el directorio. `.env` y los datos locales no se
versionan.

## Verificar la conexión

```bash
curl http://127.0.0.1:8000/api/health
```

Respuesta esperada:

```json
{"status":"ok","database":"connected"}
```

