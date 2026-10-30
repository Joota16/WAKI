# Contrato para el compañero que integra la web

Una llamada procesa **una imagen desde celular o cámara IoT**.

```python
from waki_ia import analizar_waki, guardar_resultado

reporte, imagenes = analizar_waki(
    imagen_bytes,
    contexto={
        "source": "citizen", # o "iot"
        "point_id": "CHILLON-P01",
        "captured_at": "2026-10-29T10:00:00-05:00", # solo si la plataforma la conoce
        "camera_id": None,
    },
    perfil_agua="clasico", # o chillon, pasando checkpoint local
    dispositivo="cuda",
    detectar_objetos=True,
)
archivo = guardar_resultado(reporte, imagenes, "outputs/registro_001")
```

La llamada de Python devuelve un `dict` JSON serializable y artefactos (PIL + numpy). La web puede guardar los archivos y exponer sus URLs públicas/autorizadas **desde su propio backend**.

### Campos útiles de `reporte.json`

- `input.point_id`, `input.source`, `input.captured_at`: metadatos recibidos (no calculados por IA).
- `modules.water_segmentation.status`, `.fraction_of_image_predicted_as_water`, `.model`, `.requested_profile`.
- `modules.object_candidates.model_status`: éxito/error por detector.
- `modules.object_candidates.candidates[]`: `candidate_id`, `label_es`, `source_models`, `alternate_labels`, `label_conflict`, `bbox_xyxy`, `water_relation`, `verification_status`.
- `modules.object_candidates.review_regions[]`: `region_id`, `bbox_xyxy`, `candidate_ids`, `labels_proposed`.
- `summary.candidate_count`, `summary.review_zone_count`: conteos de candidatos NO verificados; no son peligros ni objetos confirmados.
- `summary.human_review_required`: siempre true.
- `summary.risk_level`, `summary.inspection_priority`: siempre `null` (los asigna autoridad, no la IA).
- `artifacts_relative_paths`: nombres de imágenes para mostrar sobre el reporte.

### Estados a diferenciar

- `predicted_nonempty`: el modelo marcó algunos píxeles como agua. NO implica que la máscara sea correcta.
- `predicted_empty_needs_review`: no detectó agua; NO significa que esté seco.
- `error`: el módulo falló; no equivale a ausencia de evidencia.
- `candidates_found`: hipótesis para revisión, NO materiales confirmados.
- `no_candidates_detected_not_absence`: ninguna detección; NO prueba ausencia de residuos.

**IMPORTANTE:** la puntuación de un modelo no es probabilidad calibrada, y las puntuaciones de YOLOE y DINO no son comparables. El `water_relation` es un cálculo visual de solapamiento y no demuestra que un material obstaculice el flujo.

En Windows, el servidor debe reutilizar el mismo proceso de Python/GPU para que los modelos se mantengan en memoria. En producción, procesar tareas pesadas en un trabajador y no bloquear las peticiones. El módulo no hace solicitudes a internet en inferencias posteriores si los pesos ya están almacenados localmente.

## Embalaje con tu checkpoint

El ZIP de entrega inicial no tiene los pesos personalizados; el responsable del entrenamiento debe ejecutar `python scripts/empaquetar_para_web.py --checkpoint models/segformer_chillon_finetuned --out WAKI_IA_FINAL_con_checkpoint.zip` desde este proyecto. El paquete resultante se comparte al equipo web.
