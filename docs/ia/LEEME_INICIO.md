# WAKI IA — ENTREGA FINAL 4.1

**Motor independiente para el desarrollador de la plataforma web.**

## Qué se corrigió respecto a la versión híbrida 4.0

La foto de ejemplo se había segmentado con modelos diferentes:

| Perfil | Checkpoint | Resultado ya observado en esa foto |
|---|---|---|
| `clasico` (predeterminado) | `nvidia/segformer-b0-finetuned-ade-512-512` | **43.25%** de los píxeles, versión anterior v2.1 |
| `chillon` | `models/segformer_chillon_finetuned` | **28.14%** en la prueba híbrida v4, aunque obtuvo **86.18% IoU** en las 4 fotos de test independientes |

**No es un error de fusión:** v4 había seleccionado el checkpoint de 2 clases por defecto. Se mantienen ambos perfiles. Para la foto de demostración el perfil `clasico` replica el aspecto de la versión anterior; para otras escenas se debe elegir según el benchmark, no porque el área celeste sea mayor. Nunca alternar modelos de forma automática basándose solo en esa área.

## Ejecutar (Windows PowerShell)

1. Extrae el ZIP y entra a `WAKI_IA_FINAL_v4_1`.
2. Activa tu entorno Python 3.11 con PyTorch CUDA funcionando (RTX 4060):

```powershell
python -c "import torch; print(torch.cuda.is_available())"
python -m pip install -r requirements.txt
```

3. Prueba con la versión antigua del agua + detectores híbridos:

```powershell
python scripts\analizar_waki.py "ejemplo_replay\foto_de_rio.jpg" --agua clasico --device cuda --source test --point-id WAKI-DEMO --out outputs\demo_clasico
```

4. Opcional: compara el checkpoint de agua turbia (si copiaste los pesos):

```powershell
python scripts\analizar_waki.py "ejemplo_replay\foto_de_rio.jpg" --agua chillon --checkpoint "models\segformer_chillon_finetuned" --device cuda --out outputs\demo_chillon
```

Si quieres reproducir el ejemplo **sin descargar modelos**, la carpeta `ejemplo_replay/salida_validada` contiene una salida generada a partir de la máscara y predicciones guardadas. Para volverla a crear:

```powershell
python scripts\analizar_waki.py "ejemplo_replay\foto_de_rio.jpg" --replay-water-mask "ejemplo_replay\mascara_agua_anterior.png" --replay-yoloe "ejemplo_replay\predicciones_yoloe.json" --replay-dino "ejemplo_replay\predicciones_dino.json" --out outputs\replay
```

El modo `replay` **NO es una nueva inferencia ni validación del modelo**; sirve para probar el contrato y la representación.

## Archivos generados

- `reporte.json`: metadatos, módulo de agua, candidatos, zonas para revisión, errores/limitaciones.
- `original.jpg`: foto recibida.
- `mascara_agua.png`: blanco = agua para VISUALIZAR, negro = resto.
- `segmentacion.jpg`: agua superpuesta sobre la foto.
- `objetos.jpg`: zonas de revisión sin la máscara.
- `analisis_combinado.jpg`: agua + zonas.

**No reemplaces las máscaras etiquetadas del dataset por las máscaras visuales del reporte.**

## Límites y entrega

- Las 4 imágenes del conjunto test de SegFormer arrojaron IoU global 86.18% para el checkpoint propio; no garantiza ese rendimiento en otras fotos.
- Grounding DINO y YOLOE son **experimentales**: las etiquetas y coincidencias son candidatos, no objetos confirmados.
- No se calcula riesgo de inundación, caudal, altura de agua, obstrucción hidráulica ni prioridad automática.
- La plataforma gestiona reportes ciudadanos, IoT, almacenamiento, geolocalización, accesos, revisiones y fechas de captura.
- Este ZIP **NO incluye el checkpoint propio `model.safetensors`** ni los pesos de los modelos de terceros. Deben copiarse desde tu PC o descargarse por primera vez. Tampoco incluye todo el dataset de entrenamiento (no es necesario para inferencia).
- Revisa los términos de licencia de modelos dependientes de Ultralytics (AGPL-3.0/Enterprise según el caso) antes de redistribución/servicio comercial.

Para integrar Python ve `CONTRATO_PARA_WEB.md`.
