# WAKI

Arquitectura modular para monitoreo visual de ríos.

## Alcance actual

El formulario ciudadano permite registrar reportes reales con fotografías y
coordenadas del navegador o introducidas manualmente. Los datos se guardan en
SQLite y las imágenes se conservan en archivos locales. Cada registro tiene un
identificador y una página de consulta con sus fotografías.

El tablero muestra reportes ciudadanos reales, el cauce del Chillón
cartografiado en OpenStreetMap y los promedios diarios de nivel de la estación
Puente Magdalena y los caudales de Obrajillo y Puente Magdalena publicados por
SENAMHI, además de la serie meteorológica disponible de Obrajillo. El nivel de
atención del tramo utiliza la evaluación más reciente de un reporte validado,
confirmada por un administrador. La cámara del resumen recibe JPEGs
de dispositivos autenticados y muestra la última captura real. La pestaña Imágenes
vincula cada captura a su informe de IA en una ventana emergente, con original, segmentación y zonas
candidatas cuando se configura el detector. El acceso con usuario y contraseña
es opcional: el tablero y el formulario siguen siendo públicos. Los
administradores pueden validar o archivar reportes y publicar avisos de peligro
que aparecen como un popup destacado en las páginas abiertas de WAKI.
El ingreso (`/ingresar`), registro (`/registro`), revisión (`/admin/reportes`)
y publicación de avisos (`/admin/avisos`) tienen páginas propias. El menú de
cuenta enlaza directamente a estas herramientas y a **Administrar**
(`/administrar`), donde se puede cambiar la contraseña.
Todas las pantallas comparten la misma cabecera, con navegación, buscador,
campana y menú de cuenta. El buscador abre el dashboard si se utiliza desde
otra pantalla.

La tabla, el mapa y la búsqueda muestran únicamente el **río Chillón**.
Los reportes ciudadanos no solicitan río, distrito, referencia ni datos de contacto.


## Estructura

```text
app/
├── __init__.py
├── main.py                  # Inicializa FastAPI y registra las rutas
├── config.py                # Variables de entorno
├── web/
│   └── pages.py             # Tablero, formulario, listado y detalle de reportes
├── api/
│   ├── health.py            # Comprobación de conexión SQLite
│   ├── reports.py           # Creación, consulta y fotografías de reportes
│   ├── auth.py              # Registro, sesión JWT y cierre de sesión
│   ├── dependencies.py      # Autorización por rol y protección CSRF
│   ├── alerts.py            # Avisos públicos y eventos SSE
│   ├── hydrology.py         # Consulta de la caché de niveles por río
│   ├── middleware.py        # Límite del cuerpo de solicitudes
│   ├── iot.py               # Recepción binaria de imágenes con X-IoT-Key
│   └── cameras.py           # Última captura e imágenes públicas por cámara
├── schemas/
│   ├── reports.py           # Contratos y validación de reportes
│   ├── hydrology.py         # Contratos de estación, serie y estado de la fuente
│   ├── weather.py           # Precipitación y temperaturas diarias, con valores ausentes
│   └── cameras.py           # Contratos de cámaras y capturas con fechas UTC
├── services/
│   ├── reports.py           # Guardado, consultas y reintentos idempotentes
│   ├── auth.py              # Contraseñas, JWT y administrador inicial
│   ├── alerts.py            # Publicación y finalización de avisos
│   ├── hydrology.py         # Sincronización periódica de niveles diarios
│   ├── discharge.py         # Sincronización independiente de caudales
│   ├── weather.py           # Sincronización de meteorología y fechas por variable
│   ├── cameras.py           # Guardado, consulta y retención de capturas IoT
│   ├── processing.py        # Cola acotada de IA, estados, resultados y retención
│   └── images.py            # Validación, normalización y almacenamiento
├── repositories/
│   ├── reports.py           # Consultas SQL de reportes y fotografías
│   ├── users.py             # Cuentas, sesiones y límite de intentos
│   ├── alerts.py            # Avisos y registro persistente de eventos
│   ├── hydrology.py         # Lecturas diarias y estado de sincronización
│   ├── discharge.py         # Caudales por estación y fecha/hora
│   ├── weather.py           # Series meteorológicas diarias y estado de consulta
│   └── cameras.py           # SQL de capturas y retención por cámara
├── db/
│   └── database.py          # Conexiones y creación del archivo SQLite
├── integrations/
│   ├── senamhi.py           # Cliente HTTP y lector de niveles diarios
│   ├── senamhi_discharge.py # Catálogo OGC e hidrogramas de caudal
│   └── senamhi_weather.py   # Gráfico meteorológico público de Obrajillo
├── vision/
│   ├── service.py           # Contrato y selección de proveedor sin cargar modelos
│   ├── waki_ia/             # Motor IA 4.1 importado sin modificar
│   └── providers/
│       ├── waki.py          # Adaptador del motor y checkpoint local de agua
│       ├── local_dino.py    # Grounding DINO con pesos locales
│       └── local_yoloe.py   # YOLOE multiescala con pesos y prompts locales
├── templates/
│   ├── base.html            # Documento HTML y bloques comunes
│   ├── shared/              # Cabecera única, menú de cuenta y popup global de avisos
│   ├── account/             # Ingreso, registro y cambio de contraseña
│   ├── admin/               # Publicación de avisos y revisión de reportes
│   ├── reports/             # Listado paginado, tarjetas y detalle con fotografías
│   ├── dashboard/
│   │   ├── index.html       # Compone la página del tablero
│   │   ├── partials/        # Cabecera, mapa, tabla y detalle
│   │   └── tabs/            # Resumen, imágenes y reportes
│   └── citizen/
│       ├── index.html       # Compone la página del formulario
│       ├── partials/        # Cabecera, introducción, lateral, modal y pie
│       └── form/            # Secciones del formulario
└── static/
    ├── css/
    │   ├── base.css         # Reglas compartidas
    │   ├── dashboard.css    # Mapa, animaciones y barras
    │   └── citizen.css      # Formulario y miniaturas de muestra
    ├── data/                # Geometrías locales GeoJSON de los cauces OSM
    └── js/
        ├── config/          # Configuración visual de Tailwind por pantalla
        ├── dashboard/       # index.js, data.js, map.js y view.js
        ├── site/            # Sesión, moderación y avisos en todas las páginas
        └── citizen/         # Resumen, GPS, fotos, envío y confirmación
docs/prototypes/            # Los dos HTML originales de referencia
docs/ia/                    # Documentación original del motor, sin modificaciones
weights/                    # Checkpoint local de SegFormer; excluido de Git
tests/                      # Pruebas de páginas, recursos y conexión
scripts/                    # Actualización de cauces y envío de prueba IoT
.env.example
.gitignore
Dockerfile                  # Imagen Python de la aplicación
compose.yaml                # Servicio web y volumen SQLite
.dockerignore               # Limita los archivos enviados al build
requirements.txt
requirements-dev.txt        # Dependencias para ejecutar las pruebas
requirements-ai.txt         # Copia exacta de las dependencias originales del motor
```

Los paquetes Python incluyen sus archivos `__init__.py`.

## Responsabilidades y dependencias

- `main.py` ensambla la aplicación.
- `web/` entrega las páginas HTML, separado de la API JSON.
- `api/` gestiona HTTP y utilizará los servicios para las operaciones de negocio.
- `schemas/` define los contratos de entrada y salida.
- `services/` coordina casos de uso sin depender de `Request` ni `Response`.
- `repositories/` concentra SQL y utiliza `db/` para conectarse.
- `db/` administra conexiones y la inicialización del esquema.
- `vision/waki_ia/` conserva el motor original; `vision/providers/` lo conecta a los servicios.
- `templates/` compone el HTML mediante herencia e inclusiones con
  [Jinja2Templates de FastAPI](https://fastapi.tiangolo.com/advanced/templates/).
- `static/css/` define estilos y `static/js/` contiene el comportamiento del navegador.


## Organización de la interfaz

| Recurso | Responsabilidad |
| --- | --- |
| `templates/dashboard/index.html` | Ensamblar las secciones del tablero del dashboard. |
| `templates/citizen/index.html` | Ensamblar las secciones del formulario de reportes. |
| `js/dashboard/data.js` | Datos ilustrativos de ríos; sin acceso al DOM. |
| `js/dashboard/map.js` | Leaflet, capas y marcadores de reportes reales. |
| `js/dashboard/camera.js` | Última foto del ESP32, fecha, antigüedad, actualización y pantalla completa. |
| `js/dashboard/weather.js` | Tarjeta meteorológica de Obrajillo; lluvia, máximas/mínimas, fechas y valores ausentes. |
| `js/dashboard/discharge.js` | Dos tarjetas de caudal, hora de Lima, series recientes y estados por estación. |
| `js/dashboard/water-level.js` | Tarjeta del último promedio diario y gráfica de la serie publicada. |
| `js/dashboard/river-geometry.js` | Carga, validación y representación de los cauces GeoJSON. |
| `data/rivers.geojson` | Geometría y procedencia del cauce del río Chillón. |
| `js/dashboard/stations-data.js` | Nombres y coordenadas de las tres estaciones proporcionadas por el equipo. |
| `js/dashboard/stations.js` | Capa de estaciones, etiquetas, fichas y encuadre de sus puntos. |
| `js/dashboard/view.js` | Actualización de métricas, detalle y pestañas del tablero. |
| `js/dashboard/reports.js` | Consulta de los seis reportes reales más recientes, miniaturas, conteo y actualización. |
| `js/dashboard/index.js` | Conectar los eventos del tablero con mapa y vista. |
| `js/citizen/summary.js` | Resumen de zona, selección de nivel y hora. |
| `js/citizen/location.js` | Ubicación del navegador, precisión, avisos de baja precisión y entrada manual. |
| `js/citizen/attachments.js` | Selección, cámara, arrastre, vistas previas y eliminación de fotos. |
| `js/citizen/submission.js` | Envío multipart, estados de carga y reintentos sin duplicar registros. |
| `js/citizen/modal.js` | Confirmación del identificador y fecha devueltos por el servidor. |
| `js/citizen/index.js` | Inicializar los módulos del formulario. |

Las rutas de esta tabla son relativas a `app/` para las plantillas y a
`app/static/` para JavaScript. Los eventos se registran con `addEventListener`;
las plantillas no contienen JavaScript, CSS ni manejadores de eventos embebidos.

Los módulos JavaScript usan `import`/`export`. Abrir las páginas a través de
FastAPI para que las plantillas se compongan y los recursos se sirvan correctamente.

## Capturas e informes de IA

La pestaña **Imágenes** muestra capturas reales del ESP32 con fecha, estado,
original y resultado visual. El botón **Ver informe IA** abre una ventana emergente
en el tablero con el informe asociado a esa captura, separado de los reportes ciudadanos, con candidatos por zona y
descarga JSON.

La integración usa adaptadores nuevos y
`BackgroundTasks`, con cola acotada, estados persistidos y retención de originales
y resultados. Las tareas no son durables: al reiniciar, los trabajos interrumpidos
se marcan como error. Ejecutar una sola instancia con un worker.

`MODEL_PROVIDER=none` permite ejecutar sin IA. `MODEL_PROVIDER=waki` activa la
segmentación usando `weights/segformer_chillon_finetuned/` y las dependencias
opcionales. Los pesos están excluidos de Git. **Grounding DINO y YOLOE multiescala ya están
conectados**, usando los archivos locales de `weights/grounding-dino-tiny/`,
`weights/yoloe-26s-seg.pt` y `weights/waki_yoloe_prompts.npz`. Configura sus rutas
en `.env` para habilitarlos; si falta o falla un módulo, se muestra el resultado
parcial disponible.


### Probar una fotografía sin el ESP32

Abre **Imágenes → Probar con una imagen de tu equipo**, selecciona una fotografía
JPEG, PNG o WebP, introduce el valor de `IOT_KEY` de tu `.env` y pulsa
**Analizar imagen**. El resultado se abre en la ventana emergente y se actualiza
cuando termina la inferencia. La clave no se guarda en el navegador.

Las subidas se identifican como **Prueba manual** y aparecen en la galería
**Pruebas manuales** del río seleccionado. Ejecutan el mismo proveedor de IA,
pero no sustituyen la imagen del ESP32 ni crean reportes ciudadanos. Con el
configuración local actual se puede probar la segmentación de agua y los
candidatos de objetos de Grounding DINO y YOLOE. El límite de archivo es `MAX_UPLOAD_MB`.

## Cámara ESP32 lista para recibir fotografías

La cámara del resumen muestra **Esperando la primera captura del ESP32** hasta
recibir una imagen real. `POST /api/iot/upload?camera_id=chillon-01` acepta la imagen binaria
con `Content-Type: image/jpeg` y `X-IoT-Key`. Guarda el archivo normalizado y sus
fechas UTC antes de responder HTTP 201. La clave se configura mediante `IOT_KEY`
en `.env`; vacía, la recepción permanece desactivada.


Consulta el [contrato HTTP, configuración de red, script de prueba y ejemplo
ESP32](docs/esp32-camera.md). La validación se hizo con envíos simulados; queda
conectar el módulo físico de cámara y su firmware. Cada nueva captura genera un
informe de análisis o un estado explícito de IA sin configurar.

## Nivel de río publicado por SENAMHI

La tarjeta **Último nivel publicado**, junto a la cámara del resumen, consulta
`GET /api/hydrology/chillon`. Muestra **Puente Magdalena · código 111151**, el
último promedio diario disponible en metros, su fecha, la variación respecto al
promedio del día anterior cuando existe y hasta 31 fechas de la serie publicada.
El valor pertenece a esa estación, aunque el encabezado del tablero describa el
tramo de Comas.

Fuente: [gráfico público de SENAMHI](https://www.senamhi.gob.pe/mapas/mapa-estaciones-ms/map_red_graf.php?cod=111151).
El adaptador extrae exclusivamente las fechas y valores JSON que utiliza ese
gráfico. Comprueba estación, código, métrica, unidad, fechas y valores finitos;
no ejecuta JavaScript. No consulta la tabla ni las exportaciones protegidas por
CAPTCHA. Es una integración con una página pública, no una API oficial con
contrato estable; si cambia el formato, se conserva la última serie válida.

El servidor inicia una consulta en segundo plano sin bloquear el arranque y
repite cada hora. Los visitantes leen SQLite, no generan consultas a SENAMHI.
Cada ciclo actualiza lecturas por estación/fecha, incorpora correcciones y
conserva huecos como valores ausentes. Los días sin datos no se conectan en la
gráfica ni se convierten en cero. La diferencia se calcula solo entre días
consecutivos disponibles.

Configuración, también disponible en Docker Compose:

```dotenv
SENAMHI_ENABLED=true
SENAMHI_POLL_SECONDS=3600
```

El intervalo admite de 300 a 86400 segundos. Consultar más frecuentemente no
cambia la frecuencia con que SENAMHI publica los datos. El navegador vuelve a
leer la caché de WAKI cada minuto y al regresar a la pestaña. Se muestran por
separado la fecha del promedio y la fecha de la última consulta correcta, en
hora de Lima. Los promedios con más de dos días llevan un aviso de antigüedad;
si falla la fuente, aparece el error junto al último valor guardado y su fecha.
Sin lecturas se muestra un estado vacío, sin valores de ejemplo.

SQLite incorpora `hydrology_readings` y `hydrology_sync` sin borrar reportes.
Las lecturas sobreviven a reinicios. El temporizador vive en el proceso de
FastAPI: se cancela al detenerlo y vuelve a consultar al arrancar. Ejecutar con
**un worker**, como el Compose incluido, para mantener un temporizador por
integración y evitar consultas duplicadas entre procesos.
Al cambiar esta configuración con Docker,
vuelve a ejecutar `docker compose up --build -d`.

## Caudales de Obrajillo y Puente Magdalena

Los reportes ciudadanos se
conservan debajo. Cada tarjeta muestra el último caudal en **m³/s**, estación,
código, fecha/hora de Lima, serie reciente, fecha de consulta y fuente.

| Estación | Código en el visor de monitoreo | Fuente |
| --- | --- | --- |
| Obrajillo | `47E9F488` | [Monitoreo hidrológico SENAMHI](https://www.senamhi.gob.pe/servicios/?p=monitoreo-hidrologico) |
| Puente Magdalena | `111151` | [Monitoreo hidrológico SENAMHI](https://www.senamhi.gob.pe/servicios/?p=monitoreo-hidrologico) |

Obrajillo tiene otros códigos en otros catálogos; esta integración utiliza el
identificador comprobado en este visor para evitar mezclar estaciones. Ambos
puntos pertenecen a Chillón.

`GET /api/hydrology/chillon/discharge` devuelve las dos estaciones, cada una con
estado independiente, último valor, unidad, marcas UTC y hasta 72 horas de
lecturas respecto a la última fecha publicada. 

El adaptador consulta el servicio OGC WFS público de SENAMHI para conocer la
última fecha de cada estación y construye la misma consulta que usa el visor:
`mapas/mapa-monitoreohidro/include/mnt-grafica-new.php`, con `id`, `fecha_hora`,
`variable=CAUDAL` y `variable_opcion=C`. No fija la fecha de una captura ni
convierte niveles a caudales. Lee únicamente la serie `dato`; las series de
umbrales rojo/naranja/amarillo no son observaciones y no se usan como caudal.
Comprueba identidad de estación, río, variable, unidad, fechas y valores finitos
no negativos.

El hidrograma codifica la hora que muestra en marcas de milisegundos con reloj
UTC. El adaptador conserva esa hora visible como **America/Lima** y la convierte
a UTC real para guardar: por ejemplo, **29/10/2026 10:00 Lima = 15:00 UTC**.
La conversión se contrasta con los registros horarios publicados en la misma
página y se verifica en las pruebas.

La frecuencia de medición depende de la estación: en la muestra consultada,
Obrajillo publica puntos horarios y Magdalena lecturas separadas por varias
horas. La gráfica respeta las marcas publicadas y corta tramos ante valores
nulos o huecos mayores que la separación prevista; no rellena lecturas.
Los datos están sujetos a revisión por SENAMHI.

Una tarea de FastAPI consulta estas fuentes al arrancar y cada
`SENAMHI_POLL_SECONDS` (3600 por defecto), con el mismo interruptor
`SENAMHI_ENABLED`. Las consultas de nivel diario y caudal son independientes:
un fallo de una estación no borra las lecturas guardadas ni bloquea a la otra.
El navegador refresca las tarjetas desde WAKI cada minuto. Se avisa cuando el
último caudal supera 24 horas de antigüedad o falla la actualización; sin datos
se muestra un estado vacío.

## Precipitación y temperatura de Obrajillo

Hay **una sola tarjeta meteorológica**, debajo de los caudales, para
[Obrajillo en SENAMHI](https://www.senamhi.gob.pe/mapas/mapa-estaciones-ms/map_red_graf.php?cod=111159).
La ficha indica **Código 156133**, aunque el catálogo y la URL utilizan **111159**;
ambos identificadores se comprobaron.

La verificación del **29/10/2026** encontró una serie del **31/08/2026 al
30/09/2026**, con precipitación diaria en mm/día y las dos series de temperatura
completamente nulas. Por tanto:

- La lluvia publicada de **0 mm/día del 30/09/2026** se muestra con su fecha
  de publicación; no se presenta como lluvia de hoy.
- Temperatura máxima y mínima muestran **Sin datos publicados**, sin sustituir
  valores nulos por cero ni por estimaciones. La gráfica de temperaturas aparece
  únicamente cuando la fuente publique valores numéricos.
- La gráfica de precipitación conserva ceros, nulos y fechas.
  Si en el futuro hay temperaturas, se representan en un gráfico separado en °C;
  no se mezclan escalas de temperatura y precipitación.

Se comparó la ficha de **Puente Magdalena 111151** con la tarjeta de nivel ya
conectada: es la misma URL y la misma serie de nivel promedio diario en metros.
No aporta precipitación ni temperatura en esa ficha.

`GET /api/hydrology/chillon/weather` devuelve la estación, hasta 31 fechas,
último valor y fecha independientes para lluvia, temperatura máxima y mínima,
estado de la fuente y fecha de consulta correcta. `GET /api/hydrology/rimac/weather`
devuelve `not_configured`; estas lecturas no se asignan a Rímac.

El adaptador lee solo los arrays literales del gráfico público, sin ejecutar
JavaScript ni acceder a tablas o exportaciones protegidas por CAPTCHA. Valida
la identidad meteorológica, código publicado, nombres de las tres series,
unidades, longitud de arrays, fechas, valores finitos y precipitación no
negativa. Las temperaturas negativas y el cero publicado son valores válidos.
Si cambia el formato o falla la fuente, se conserva la última serie guardada y
se informa del error.

La consulta ocurre al arrancar y cada `SENAMHI_POLL_SECONDS` (3600 por defecto),
independientemente del nivel y el caudal, y se desactiva con `SENAMHI_ENABLED=false`.
El navegador solo lee SQLite a través de WAKI cada minuto. Consultar cada hora
no hace más reciente una serie que SENAMHI publica en tiempo diferido.
Las tablas `weather_readings` y `weather_sync` conservan las lecturas y el estado
al reiniciar, sin cambiar reportes, niveles ni caudales. Cada métrica muestra su
propia fecha. La API conserva el estado de antigüedad; la tarjeta no muestra
un aviso adicional por superar dos días.

## Cauces de los ríos

El mapa utiliza `app/static/data/rivers.geojson`, una copia local de los ejes
cartografiados en OpenStreetMap. Sustituye las líneas ilustrativas del prototipo:

| Río | Fuente OSM | Tramos | Puntos |
| --- | --- | --- | --- |
| Chillón | [Relación 11643078](https://www.openstreetmap.org/relation/11643078) | 7 | 3196 |

Fecha de la base consultada: **2026-10-29T07:56:02Z**. Se conservan las coordenadas
de las vías del cauce principal, en un `MultiLineString` por río, sin unir extremos
separados ni inventar curvas. Los marcadores de tramo se ubican sobre nodos del
cauce. Las estaciones conservan sus coordenadas originales.

El archivo se sirve desde WAKI; arrancar la aplicación o visitar el tablero no
consulta Overpass. Si falla su carga, se muestra un error con **Reintentar**, sin
sustituirlo por líneas ficticias. Para actualizarlo manualmente:

```bash
python scripts/update_river_geometry.py
# O importar una respuesta Overpass previamente descargada:
python scripts/update_river_geometry.py --input /ruta/a/respuesta-overpass.json
```

El script usa solo la biblioteca estándar, valida la relación del Chillón y escribe
el archivo de forma atómica. Conserva identificadores de origen, fecha de la
fuente y hash SHA-256 de la respuesta para trazabilidad. Al cambiar este archivo,
reconstruye el contenedor si utilizas Docker.

Datos © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
distribuidos bajo [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
Los cauces son cartografía: su detalle depende del levantamiento disponible y no
representa los bordes actuales del agua, profundidad, caudal ni riesgo. Los colores
y métricas del diseño siguen siendo ilustrativos.

## Estaciones hidrológicas en el mapa

Los tres puntos se muestran con un marcador morado **EH**, separado de los
marcadores de reportes y de los cauces cartografiados. Se conservan las
coordenadas proporcionadas por el equipo:

| Estación | Latitud | Longitud |
| --- | --- | --- |
| Malecón Chillón | -11.913546150295304 | -77.07124450899127 |
| Obrajillo | -11.45243385271647 | -76.6221144437565 |
| Puente Magdalena | -11.69463 | -76.83719 |

La vista inicial abarca las tres estaciones. El botón **Ver estaciones** vuelve
a encuadrarlas, y el buscador permite encontrarlas por su nombre, con o sin
tildes. Al pulsar un punto se abre su nombre, tipo y coordenadas. La capa de
estaciones se mantiene activa en los modos de tramos y de reportes recientes.


## Instalación y ejecución

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

Abrir las siguientes rutas:

- http://127.0.0.1:8000/ — tablero de monitoreo.
- http://127.0.0.1:8000/reportar — formulario ciudadano.
- http://127.0.0.1:8000/reportes — listado de reportes guardados con fotografías.
- http://127.0.0.1:8000/docs — documentación de la API.

Los enlaces de las pantallas permiten navegar entre el tablero y el formulario.
Al iniciar se crea `data/waki.sqlite3` con las tablas `reports` y `report_photos`.
Las fotografías se guardan en `data/photos/` con nombres generados por el servidor.
`DATA_DIR` permite cambiar el directorio. `.env` y los datos locales no se
versionan.

## Ejecutar con Docker Compose

Requiere Docker y Docker Compose. Desde la raíz del repositorio:

```bash
docker compose up --build -d
```

No necesitas instalar Python ni crear `.venv` para esta opción. Tampoco es
necesario crear `.env`: hay valores predeterminados. Si ya existe, Compose
utiliza las variables documentadas en `.env.example`, incluida la clave IoT
si se configura.

- Tablero: http://localhost:8000/
- Formulario: http://localhost:8000/reportar
- Reportes guardados: http://localhost:8000/reportes
- Estado: http://localhost:8000/api/health

Para utilizar otro puerto, cambia `WAKI_PORT` en `.env` o ejecútalo así:

```bash
WAKI_PORT=8001 docker compose up --build -d
```

En ese caso, abre http://localhost:8001/. El puerto se publica en la interfaz
local `127.0.0.1` por defecto; `WAKI_BIND_ADDRESS` permite configurar el acceso
desde otros equipos cuando se necesite para el ESP32.

La aplicación se ejecuta con un usuario sin privilegios y guarda SQLite en
`/app/data/waki.sqlite3`, dentro del volumen `waki_data` del proyecto Compose.
Ese volumen se conserva al detener o recrear el contenedor; es independiente
del directorio `data/` utilizado al ejecutar Python directamente. Compose fija
`DATA_DIR=/app/data` para que los datos queden dentro del volumen.

Comandos habituales:

```bash
docker compose ps
docker compose logs -f waki
docker compose down
```

El servicio comprueba `/api/health` periódicamente. Para aplicar cambios del
código, vuelve a ejecutar `docker compose up --build -d`; el contenedor ejecuta
Uvicorn sin recarga automática. La configuración usa el formato de la
[especificación de Docker Compose](https://docs.docker.com/reference/compose-file/services/).

## Reportar con fotografías y ubicación

En `/reportar`, indica la condición que observaste, marca las situaciones que
correspondan y adjunta tus fotografías. Puedes añadir una descripción y
coordenadas opcionales. No se solicitan datos de zona ni de contacto.

«Usar mi ubicación actual» solicita permiso al navegador. Muestra las coordenadas
y su precisión aproximada; no supone que tu ubicación sea el lugar fotografiado.
Comprueba el enlace al mapa antes de enviarla. Si se deniega el permiso, no hay
señal o se agota el tiempo, puedes volver a intentarlo, introducir coordenadas
manualmente o enviar el reporte sin coordenadas.

El navegador no indica qué tecnología utilizó para obtener la posición. Pedir
alta precisión no garantiza una lectura de GPS ni una dirección exacta. WAKI
muestra el radio de precisión comunicado por el navegador y avisa cuando supera
500 metros; este umbral es una decisión de interfaz, no una garantía de
exactitud. El aviso también aparece al consultar un reporte ya guardado.
Una lectura de 18 726 metros se muestra como aproximadamente 18,7 km, sin
cambiar las coordenadas ni la precisión originales almacenadas.

La geolocalización requiere **HTTPS**, salvo en `localhost`, y depende del permiso
y del servicio de ubicación del dispositivo. Véase la
[documentación de geolocalización](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation/getCurrentPosition).

Puedes seleccionar fotos, arrastrarlas o usar «Tomar una foto» en un celular
compatible. Se muestran las miniaturas y se pueden quitar antes de enviar.
Por defecto se admite de 1 a 5 fotografías JPEG, PNG o WebP de hasta 8 MB y
20 millones de píxeles cada una. No se admiten videos, HEIC ni imágenes animadas.

El servidor comprueba el contenido real, corrige la orientación y normaliza las
fotografías a JPEG con un lado máximo de 1920 píxeles, eliminando EXIF. Los límites
se configuran con `MAX_PHOTOS`, `MAX_UPLOAD_MB`, `MAX_IMAGE_PIXELS` y
`NORMALIZED_MAX_SIDE`, también disponibles en Compose.

La confirmación solo aparece tras guardar el reporte. Si falla la conexión o la
validación, los datos y fotos permanecen en el formulario para reintentar.
Los reintentos del mismo envío usan una clave de idempotencia para evitar
duplicados. El enlace `/reportes/{id}` permite comprobar las fotos guardadas.

Las fotografías, observaciones y coordenadas de los reportes disponibles son
consultables públicamente. No se recogen datos de contacto. Al arrancar sobre
una base anterior se retiran las columnas de río, distrito, referencia,
anonimato, nombre, teléfono y barrio. Se conservan identificadores, fechas,
fotografías, coordenadas, observaciones y revisiones.

## Consultar los reportes guardados

El enlace **Reportes** de la cabecera abre `/reportes`. Muestra los registros de
ciudadanos con miniatura, identificador, observación, fecha en hora de Lima y
enlace a los datos y fotografías. El orden es del más reciente al más antiguo,
con 12 registros por página. La navegación «Anterior» y «Siguiente» recorre el
listado completo; también puedes usar `/reportes?page=2`.

La pestaña **Reportes** del tablero y el recuadro «Últimos reportes ciudadanos»
consultan los seis registros más recientes, sin depender del tramo de
demostración seleccionado. «Ver todos los reportes» abre el listado completo.
«Actualizar» vuelve a consultar la base; también se actualiza al regresar a la
pestaña del navegador.

La capa «Reportes recientes» del mapa utiliza esos mismos registros y solo
representa los que tengan coordenadas. Cada marcador abre el reporte guardado.
Los registros sin coordenadas siguen apareciendo en el listado. Se muestran
estados de carga, vacío y error, sin sustituir los registros por datos ficticios.

## API de reportes

- `POST /api/reports`: formulario multipart con `metadata` JSON y uno o más campos
  `files`. Responde HTTP 201 con el registro guardado. Acepta opcionalmente
  `Idempotency-Key` con un UUID; reutilizarlo con otro contenido devuelve HTTP 409.
- `GET /api/reports?limit=12&offset=0`: listado paginado.
- `GET /api/reports/{id}`: consulta del registro.
- `GET /api/reports/{id}/photos/{photo_id}`: fotografía normalizada.

Ejemplo de envío:

```bash
curl http://localhost:8000/api/reports \
  -F 'metadata={"observed_condition":"normal","observations":"Agua visible en el cauce","latitude":-11.8924,"longitude":-77.0682}' \
  -F 'files=@/ruta/a/foto.jpg'
```

## Verificar la conexión

```bash
curl http://127.0.0.1:8000/api/health
```

Respuesta esperada:

```json
{"status":"ok","database":"connected"}
```

## Comprobaciones

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Las pruebas usan SQLite y archivos temporales. Verifican páginas, recursos,
recepción de fotos, contenido real, límites, coordenadas, privacidad, eliminación
de EXIF, reintentos, persistencia, listado paginado, privacidad del listado y
limpieza de archivos ante fallos. También comprueban la integridad de la
cartografía local y que su importación conserve los tramos del cauce principal.
La integración SENAMHI se prueba con un fragmento público guardado y transporte
HTTP simulado: identificación de estación, unidades, nulos, cambios de formato,
fallos de red, correcciones, persistencia, cancelación y aislamiento de Rímac.
Los caudales se comprueban con muestras de ambas estaciones, catálogo simulado,
unidades, horas de Lima, correcciones, fallos independientes y conservación de
lecturas. La meteorología comprueba la separación entre cero y ausencia,
temperaturas negativas, unidades, códigos de la ficha y del catálogo, datos
antiguos, fallos, persistencia y ausencia de una tarjeta duplicada de Magdalena.
Las capturas IoT prueban autenticación, JPEG real, fechas, EXIF, tamaño,
retención, reinicios y aislamiento respecto a los reportes ciudadanos.
Las cuentas comprueban registro, contraseñas, JWT inválidos y vencidos,
revocación al cerrar sesión, roles, CSRF y límite de intentos. La moderación
verifica que el archivo conserve registros y fotografías y los oculte al público,
así como la restauración, el historial y los conflictos entre revisores. Los
avisos comprueban permisos, persistencia y eventos públicos sin datos privados.
Las pruebas no consultan servicios externos.

## Límites de las pantallas

Se conserva el diseño de los prototipos y se unifica el nombre como WAKI.
La tarjeta del último nivel utiliza promedios diarios publicados por SENAMHI
y las dos tarjetas de caudal utilizan sus hidrogramas horarios publicados.
La tarjeta meteorológica muestra precipitación y, cuando existan, temperaturas
máximas/mínimas de la fuente de Obrajillo, con fechas y ausencia de datos explícitas.
El nivel de atención es una evaluación preventiva asignada por el administrador,
con fecha y reporte de respaldo. Sin evaluación aparece en gris.

El formulario, el listado, las miniaturas y la capa de reportes utilizan datos
reales. Los cauces utilizan cartografía OSM; los niveles de Puente Magdalena
proceden de SENAMHI. Ambos son independientes de los reportes registrados.



