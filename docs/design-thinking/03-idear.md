# 3. Idear: alternativas antes de elegir tecnología

[← Anterior](02-definir.md) | [Índice](README.md) | [Siguiente →](04-prototipar.md)

## Brainstorming

| Ideas | Descripción |
|---|---|
| Integrante 1 | Implementar un sistema de cámaras de bajo costo para obtener fotografías periódicas de tramos ribereños y observar sus condiciones. |
| Integrante 2 | Complementar las cámaras con reportes ciudadanos que incluyan fotografías, ubicación y descripción de posibles incidencias. |
| Integrante 3 | Integrar las cámaras y los reportes ciudadanos en una plataforma digital con un mapa para visualizar y localizar las incidencias. |
| Integrante 4 | Incorporar información meteorológica e hidrológica oficial para complementar las fotografías y los reportes ciudadanos. |
| Integrante 5 | Añadir criterios de atención preliminar para identificar y priorizar los tramos ribereños que requieren evaluación técnica preventiva. |

## Matriz de priorización (NOW–WOW–HOW)

| Cuadrante | Criterio de clasificación | Ideas evaluadas |
|---|---|---|
| **Now** | Alta factibilidad; valor claro; familiar para usuarios. | Registro de reportes ciudadanos georreferenciados; mapa digital de incidencias; visualización de información hidrometeorológica disponible en fuentes oficiales. |
| **Wow** | Alto valor y atractivo; implementación realizable en el MVP. | Sistema de cámaras de bajo costo para capturar imágenes periódicas; plataforma que integre imágenes, reportes ciudadanos y datos hidrometeorológicos; criterios de priorización preliminar de tramos ribereños. |
| **How** | Interesante pero aún incierta por costo, permiso, datos o seguridad. | Ampliar la red de cámaras; automatizar la detección de cambios en las imágenes; incorporar nuevos sensores locales; desarrollar modelos con mayor precisión. |
| **Descartar / Posponer** | Sin evidencia de necesidad o riesgo no controlable. | Emitir alertas oficiales de inundación; confirmar automáticamente un desborde mediante una fotografía; realizar predicciones autónomas sin modelos hidrológicos validados. |

## Mapa de concepto

| Campo | Descripción |
|---|---|
| Nombre | WAKI: Sistema inteligente y colaborativo para la observación preventiva de tramos ribereños ante el incremento del riesgo de inundaciones |
| Descripción | Sistema que integra fotografías captadas mediante cámaras de bajo costo, reportes ciudadanos georreferenciados e información hidrometeorológica oficial disponible. Mediante una plataforma web, la información se organiza y se aplican criterios preliminares de priorización para identificar los tramos que requieren evaluación técnica preventiva. |
| Público objetivo | Actores involucrados en la Gestión del Riesgo de Desastres y/o atención de emergencias; población local. |
| Beneficios | Centraliza información dispersa, facilita la ubicación de incidencias, permite consultar evidencias visuales y ayuda a organizar la atención preventiva de los tramos ribereños. |
| Actores involucrados | Equipo desarrollador de WAKI, personal municipal de GRD, serenazgo, población local, SENAMHI y ANA, según sus competencias y la disponibilidad de información. |
| Boceto | Ver [Bocetos](#bocetos) (ANX-06). |

### Bocetos

| ID | Pantalla | Imagen |
|---|---|---|
| ANX-06-a | Pantalla 1 | **Pendiente:** `anexos/img/idear/anx-06-a-boceto-pantalla-1.jpg` |
| ANX-06-b | Pantalla 2 | **Pendiente:** `anexos/img/idear/anx-06-b-boceto-pantalla-2.jpg` |
| ANX-06-c | Pantalla 3 | **Pendiente:** `anexos/img/idear/anx-06-c-boceto-pantalla-3.jpg` |

> **Imágenes pendientes:** agregar los bocetos en [`anexos/img/idear/`](anexos/img/idear/) con los nombres indicados y reemplazar cada celda por `![ANX-06-x: boceto pantalla n](anexos/img/idear/anx-06-x-boceto-pantalla-n.jpg)`. Las pantallas del prototipo ya implementado están en [Prototipar](04-prototipar.md#secuencia-de-pantallas) (ANX-04 y ANX-05).

## Propuesta de valor

| Elemento | Respuesta |
|---|---|
| Insight | La identificación y priorización de tramos ribereños que requieren atención preventiva no depende únicamente de disponer de información sobre las condiciones del río, sino de integrar y verificar oportunamente datos hidrológicos oficiales, reportes ciudadanos y observaciones visuales, considerando las limitaciones de monitoreo y verificación en campo. |
| Nombre de la solución | WAKI: Sistema inteligente y colaborativo para la observación preventiva de tramos ribereños ante el incremento del riesgo de inundaciones |

### Canvas de la propuesta de valor: perfil del usuario

| Elemento | Contenido |
|---|---|
| Hace y necesita | Consultar información de las condiciones del río, revisar reportes ciudadanos, localizar incidencias, contrastar fotografías y datos oficiales, y priorizar tramos que requieren evaluación técnica preventiva. |
| Dolores | Información distribuida entre distintas fuentes; limitaciones para verificar incidencias en campo; recursos operativos limitados; posibles reportes falsos o incompletos; falta de información localizada sobre algunos tramos. |
| Beneficios | Consultar información integrada; localizar evidencias; comparar fotografías y reportes; distinguir incidencias pendientes de verificación; organizar la priorización de evaluaciones preventivas. |

### Canvas de la propuesta de valor: mapa de valor

| Elemento | Contenido |
|---|---|
| Productos y servicios | Plataforma web y aplicación móvil, cámaras de bajo costo para captura visual, registro de reportes ciudadanos e integración de información hidrometeorológica disponible. |
| Liberadores de dolor | Centraliza fuentes de información, organiza reportes por ubicación y fecha, permite consultar evidencias visuales y diferencia los reportes recibidos de los verificados. |
| Generadores de beneficios | Facilita la identificación de evidencias por tramo, permite visualizar las incidencias recurrentes y ayuda a priorizar los sectores que requieren evaluación técnica preventiva. |

### Resumen de la propuesta de valor

| | |
|---|---|
| **Nuestros** | Usuarios son el personal municipal y actores involucrados en la atención de emergencias a nivel local; población local |
| **Ayudan** | WAKI, mediante un sistema que integra cámaras de bajo costo, reportes ciudadanos e información hidrometeorológica oficial disponible. |
| **A** | Identificar y priorizar preliminarmente los tramos ribereños que requieren evaluación técnica preventiva. |
| **Con** | Información georreferenciada, evidencias visuales y criterios preliminares de atención organizados en una sola plataforma, sin sustituir las inspecciones ni los procedimientos oficiales. |

## Journey Map ideal (TO-BE)

Las referencias entre paréntesis remiten a la entrevista (MUN-01, MUN-02) y al objetivo de la guía de entrevista (Obj.). Ver [evidencias.md](evidencias.md).

| # | Pasos, momentos | Emociones | Qué se está solucionando |
|---|---|---|---|
| 1 | La cámara WAKI del tramo capta imágenes periódicas. La plataforma se actualiza con los datos del SENAMHI (Obrajillo, Puente Magdalena y avisos hidrológicos). | Tranquilidad: "el tramo se está observando aunque no haya estación en mi distrito". | Falta de estaciones hidrométricas locales (MUN-01 · Obj. 02) |
| 2 | Un vecino ve acumulación de residuos. Desde el celular envía un reporte con foto, ubicación automática y tipo de incidencia, en pocos toques y sencillo. | Preocupación, que pasa a "alguien me va a escuchar" (idealmente). | Se provee una herramienta no técnica que no pide datos UTM, pero que aún así obtiene la información relevante de ubicación y fecha (MUN-01 · Obj. 03) |
| 3 | El reporte aparece en la plataforma para el personal con una etiqueta de "pendiente por revisar". | Alerta y atento, pero sin pánico. | Reportes dispersos entre llamadas y WhatsApp (MUN-01 · Obj. 01) |
| 4 | El personal de la municipalidad abre el tramo donde hubo el reporte y lo compara con la foto enviada, además de imágenes anteriores. | Transición duda–confianza. | Hoy se verifica mandando serenazgo o la camioneta cada vez (MUN-01 y MUN-02 · Obj. 02) |
| 5 | En la misma vista puede verificar los datos hidrológicos de caudal, nivel del río y avisos vigentes. | Respaldo y tranquilidad. | Fuentes dispersas; necesidad de información sistematizada de aguas arriba (MUN-02 · Obj. 02) |
| 6 | WAKI sugiere un nivel de prioridad, el cual será confirmado por el personal, con lo cual se verifica el reporte. | Claridad y control. | Falsas alarmas y pérdida de credibilidad (MUN-02 · Obj. 02) |
| 7 | Una vez priorizados los tramos, se programa una inspección técnica y se envían recursos donde hacen falta. | Alivio, eficiencia y dirección. | Pocos recursos operativos: "una o dos camionetas" (MUN-01 · Obj. 02) |
| 8 | Se comunica por los canales existentes a los actores que participarán en la limpieza del río (serenazgos, dirigentes) con evidencia fotográfica. | Seguridad al comunicar con pruebas y dirección, pues se implementan canales ya conocidos. | Credibilidad: "mostrar información más sólida y los cambios del río" (MUN-02 · Obj. 02) |
| 9 | El resultado es registrado. En caso de que los reportes dirijan la interpretación a la de una emergencia, el personal podrá generar un aviso a los usuarios que están usando WAKI. | El vecino se siente tomado en cuenta y podría sentir disposición a volver a reportar. | Los puntos críticos se definen por antecedentes (MUN-01 · Obj. 01); confianza en la herramienta (MUN-02 · Obj. 03) |
