# Anexos de imágenes

[← Evidencias](../evidencias.md) | [Índice](../README.md)

Imágenes que no cupieron en la ficha técnica. Cada archivo se nombra con su ID de evidencia, en minúsculas y sin espacios (por ejemplo `obs-01-f01.jpg`).

## Índice

| ID | Descripción | Fase | Archivo | Dónde se cita | Estado |
|---|---|---|---|---|---|
| OBS-01-F01 | Margen con vegetación alta y talud de tierra expuesto | Empatizar | `img/empatizar/obs-01-f01.jpg` | [01-empatizar.md](../01-empatizar.md#obs-01-f01) | Pendiente |
| OBS-01-F02 | Cauce con vegetación herbácea, residuos y agua estancada | Empatizar | `img/empatizar/obs-01-f02.jpg` | [01-empatizar.md](../01-empatizar.md#obs-01-f02) | Pendiente |
| OBS-01-F03 | Desmonte con sacos y residuos sólidos hasta el borde del cauce | Empatizar | `img/empatizar/obs-01-f03.jpg` | [01-empatizar.md](../01-empatizar.md#obs-01-f03) | Pendiente |
| ANX-01 | Boceto, pantalla 1 | Idear | `img/idear/anx-01-boceto-pantalla-1.jpg` | [03-idear.md](../03-idear.md#bocetos) | Pendiente |
| ANX-02 | Boceto, pantalla 2 | Idear | `img/idear/anx-02-boceto-pantalla-2.jpg` | [03-idear.md](../03-idear.md#bocetos) | Pendiente |
| ANX-03 | Boceto, pantalla 3 | Idear | `img/idear/anx-03-boceto-pantalla-3.jpg` | [03-idear.md](../03-idear.md#bocetos) | Pendiente |
| ANX-04 | Storyboard del flujo vecino → plataforma → personal GRD | Prototipar | `img/prototipar/anx-04-storyboard.jpg` | [04-prototipar.md](../04-prototipar.md#imágenes-del-prototipo) | Pendiente |
| ANX-05 | Modelo CAD de la carcasa (Onshape) | Prototipar | `img/prototipar/anx-05-carcasa-cad.png` | [04-prototipar.md](../04-prototipar.md#imágenes-del-prototipo) | Pendiente |
| ANX-06 | Capturas del sitio web WAKI | Prototipar | `img/prototipar/anx-06-captura-*.png` | [04-prototipar.md](../04-prototipar.md#secuencia-de-pantallas) | Pendiente |

La carpeta [`img/evaluar/`](img/evaluar/) queda reservada para la fase Evaluar.

## Cómo agregar una imagen

1. Copia el archivo a la subcarpeta de su fase con el nombre indicado en la tabla.
2. Si pesa más de 1 MB, redúcelo a un ancho máximo de 1600 px. Por ejemplo, con ImageMagick:
   `magick entrada.jpg -resize "1600x>" -quality 85 obs-01-f01.jpg`
3. Verifica que no aparezcan personas, rostros ni placas identificables.
4. En el documento de la fase, reemplaza el bloque "Imagen pendiente" por la referencia Markdown, por ejemplo:
   `![OBS-01-F01: talud expuesto](anexos/img/empatizar/obs-01-f01.jpg)`
5. Cambia el **Estado** de la fila a "Agregada". Si agregas una imagen nueva, usa el siguiente ID libre (ANX-07, ANX-08…).
