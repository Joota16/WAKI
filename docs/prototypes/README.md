## Proceso de desarrollo del prototipo

El prototipo de WAKI se desarrolló mediante iteraciones que combinaron el diseño del dispositivo, la captura y transmisión de fotografías, el procesamiento de imágenes y la presentación de evidencias en una plataforma web. Cada componente permitió explorar una parte de la propuesta: observar el entorno ribereño, incorporar reportes ciudadanos y facilitar su revisión por personal municipal.

El proceso permitió construir un prototipo funcional y reconocer aspectos que requieren ajustes antes de una instalación permanente o de su uso para apoyar decisiones operativas.

### 1. Del concepto al diseño del dispositivo

Se propuso una carcasa con forma de rana para dar una identidad reconocible al dispositivo WAKI. El boceto exploró la apariencia frontal y lateral, la ubicación de la cámara y el espacio disponible para alojar los componentes electrónicos.

En el boceto se plantearon dimensiones aproximadas de 160 mm de ancho, 150 mm de alto y 90 mm de profundidad. Estas medidas corresponden a una propuesta de diseño y deben contrastarse con las dimensiones del modelo CAD y de las piezas fabricadas.

La cámara se ubicó conceptualmente en la zona frontal, próxima a la boca, para mantener visible el lente e integrarlo en la apariencia del dispositivo. También se consideró el acceso al interior para facilitar el montaje, la alimentación y el mantenimiento.

El diseño se trabajó en Onshape como parte de su preparación para fabricación mediante impresión 3D. La forma exterior, la distribución interna y el sistema de sujeción constituyen elementos que deben ajustarse conjuntamente: una carcasa reconocible también debe permitir un encuadre útil y un montaje estable.

### 2. Construcción e integración del módulo de captura

Se utilizó una ESP32-CAM con conexión Wi-Fi para obtener fotografías y enviarlas al servidor de WAKI. Durante el desarrollo se realizaron capturas de prueba para comprobar la comunicación antes de utilizar imágenes del entorno ribereño.

El firmware permite configurar la identificación de la cámara, el destino de envío y la clave de autenticación. En la configuración de prueba se estableció un intervalo de captura de aproximadamente un minuto.

La función del dispositivo es capturar y transmitir fotografías. Los modelos de visión computacional se ejecutan en el servidor, no dentro de la ESP32-CAM.

Esta separación permitió utilizar un dispositivo de captura de recursos limitados y realizar el procesamiento en un equipo con mayor capacidad de cómputo.

### 3. Prueba de posicionamiento en el entorno ribereño

Se realizó una prueba de posicionamiento del prototipo junto al río. Las fotografías de esta actividad documentan el dispositivo próximo a una baranda y la vista disponible del cauce, la vegetación y las márgenes.

Esta aproximación permitió explorar cómo la ubicación y la orientación de la cámara condicionan la evidencia obtenida. Se identificaron aspectos que deben revisarse durante el montaje:

- Mantener el lente libre de obstrucciones producidas por la carcasa o el soporte.
- Orientar la cámara hacia un tramo de interés y conservar referencias visibles de las márgenes.
- Reducir movimientos que dificulten comparar capturas sucesivas.
- Comprobar la disponibilidad de alimentación y conectividad.
- Diseñar una fijación que permita revisar el dispositivo sin comprometer su estabilidad.

Las fotografías documentan una prueba de ubicación; no acreditan por sí solas una instalación permanente, resistencia a la intemperie o transmisión continua desde ese punto.

### 4. Desarrollo de la plataforma web

La plataforma se desarrolló para reunir evidencias y permitir su consulta desde computadora o celular. Se incorporaron vistas para el registro de reportes ciudadanos, la consulta de información del tramo y la revisión institucional.

El flujo ciudadano permite registrar una observación y adjuntar evidencia. El flujo institucional permite revisar los reportes y decidir su validación o descarte, así como gestionar avisos.

Se diferenció la observación enviada por un ciudadano de la información revisada por un administrador. Un reporte pendiente no se presenta como un hecho confirmado ni implica que se haya realizado una intervención municipal.

La información hidrológica se incorporó como una fuente complementaria. Las mediciones de una estación deben interpretarse con su ubicación y fecha; no representan una medición directa del nivel del agua en el punto donde se encuentra la cámara.

### 5. Integración del procesamiento de imágenes

Se integraron módulos de visión computacional con funciones diferentes:

| Módulo | Función dentro del prototipo |
|---|---|
| Segmentación de agua | Identificar píxeles que el modelo clasifica como agua y calcular su proporción respecto de la imagen. |
| YOLOE multiescala | Proponer candidatos de objetos para revisión. |
| Grounding DINO | Proponer candidatos a partir de las categorías o descripciones configuradas. |

El servidor conserva la fotografía original y genera un registro de análisis. Cuando los modelos están configurados, procesa la imagen y guarda los resultados disponibles para mostrarlos en un informe.

El flujo implementado es:

1. La ESP32-CAM captura una fotografía.
2. El dispositivo la envía al servidor mediante una solicitud autenticada.
3. El servidor almacena la captura y registra el trabajo de análisis.
4. Los modelos procesan la imagen.
5. La plataforma permite consultar el original, las visualizaciones y las observaciones del resultado.

También se incorporó una función de prueba manual para analizar fotografías sin depender de la disponibilidad física de la cámara.

### 6. Ajustes realizados durante la integración

Durante las primeras pruebas se recibieron fotografías cuando el procesamiento de IA no estaba configurado. Estas capturas se conservaron y la plataforma mostró el estado correspondiente, sin atribuirles resultados que no se habían generado.

Posteriormente se configuraron las dependencias, las rutas de los modelos y la ejecución mediante GPU NVIDIA con CUDA. Se habilitó el reprocesamiento de capturas conservadas y se realizaron pruebas manuales para comprobar la generación de informes.

La aplicación se ejecutó mediante Docker Compose. Los datos se almacenaron en un volumen persistente para conservar fotografías, reportes e informes al reconstruir o reemplazar el contenedor.

También se retiraron registros de prueba seleccionados para ordenar la evidencia presentada en la plataforma. Antes de esas eliminaciones se generaron respaldos.

### 7. Resultados observados y aprendizajes

Las pruebas manuales permitieron comprobar la carga de imágenes, la ejecución de los módulos y la presentación de resultados en la web.

Sin embargo, completar un análisis no garantiza que su interpretación sea correcta. En una fotografía con agua visible, el módulo de segmentación devolvió una proporción de 0,0 %. Este resultado evidencia la necesidad de revisar el comportamiento del modelo con imágenes representativas del lugar de uso.

Asimismo, los recuadros de detección se presentan como candidatos para revisión humana. Las etiquetas propuestas y las puntuaciones de los detectores no equivalen a objetos confirmados ni a probabilidades de acierto.

| Aprendizaje | Implicación para la siguiente iteración |
|---|---|
| El encuadre afecta la información disponible. | Ajustar ubicación, orientación y fijación de la cámara. |
| Recibir una fotografía no garantiza que se haya analizado. | Mostrar por separado el estado de recepción y el estado de procesamiento. |
| Una máscara vacía puede aparecer en una escena con agua. | Revisar el modelo, el preprocesamiento y la interpretación de sus clases antes de utilizar el resultado. |
| Los detectores pueden proponer candidatos imprecisos. | Conservar el original y facilitar la revisión de cada recuadro. |
| El funcionamiento depende de alimentación, red y servidor. | Evaluar continuidad de servicio y recuperación ante interrupciones. |
| La reconstrucción de la aplicación debe conservar la evidencia. | Mantener almacenamiento persistente y respaldos verificables. |

### 8. Alcance del prototipo construido

WAKI alcanzó una integración funcional de captura, almacenamiento, procesamiento y consulta de evidencias. La plataforma permite explorar cómo pueden reunirse fotografías de cámara, reportes ciudadanos e información hidrológica para apoyar una revisión institucional.

Este alcance no equivale a una validación de precisión de los modelos ni a una demostración de eficacia preventiva en condiciones reales.

| Componente | Evidencia o estado |
|---|---|
| Captura y envío desde ESP32-CAM | Se realizaron pruebas de recepción de fotografías. |
| Almacenamiento de evidencias | Se conservaron capturas, reportes e informes en la base de datos y el almacenamiento de la aplicación. |
| Procesamiento de IA | Se comprobó la generación de informes mediante pruebas manuales. |
| Visualización web | Se mostraron originales, resultados y observaciones del análisis. |
| Carcasa | Se desarrollaron el boceto y el trabajo de diseño para el prototipo físico. |
| Posicionamiento en campo | Se documentó una prueba de ubicación junto al cauce. |
| Funcionamiento continuo | Requiere pruebas de duración, conectividad y recuperación ante fallos. |
| Flujo ESP32-CAM → IA después de la última integración | Requiere una nueva prueba completa con el dispositivo. |
| Despliegue en AWS | Se preparó un respaldo para trasladar los datos; su entrega no acredita que la restauración o el despliegue hayan concluido. |

### 9. Aspectos pendientes para la siguiente iteración

- Comprobar el recorrido completo de una captura nueva desde la ESP32-CAM hasta su informe de IA.
- Evaluar la segmentación con fotografías representativas del río y referencias anotadas.
- Revisar las etiquetas y los recuadros de los objetos candidatos.
- Incorporar recuperación de trabajos de análisis interrumpidos por reinicios.
- Evaluar la autonomía, la estabilidad del montaje y la protección del dispositivo frente a las condiciones ambientales.
- Probar con vecinos y personal de GRD la comprensión de los estados, resultados y avisos.
- Verificar el despliegue y la restauración de datos en el entorno de destino.

El prototipo no mide profundidad, nivel ni caudal mediante las fotografías. Tampoco predice desbordes, confirma inundaciones o determina automáticamente la necesidad de evacuación. Su función es reunir y presentar evidencias para una revisión humana.
