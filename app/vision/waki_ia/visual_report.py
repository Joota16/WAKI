"""Orquestador del análisis de evidencia WAKI 2.0 (independiente de backend).

NO calcula caudal, nivel, probabilidad de inundación ni riesgo automático.
Los modelos pueden fallar: toda observación de IA debe revisarse por un humano.
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .inference import predict_image
from .spatial_analysis import enrich_candidates


def open_image(value: Image.Image | bytes | str | Path) -> Image.Image:
    if isinstance(value, Image.Image):
        return ImageOps.exif_transpose(value).convert("RGB")
    if isinstance(value, bytes):
        with Image.open(io.BytesIO(value)) as im:
            return ImageOps.exif_transpose(im).convert("RGB")
    with Image.open(value) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def quality_indicators(image: Image.Image) -> dict[str, Any]:
    """Señales heurísticas SIN calibrar; no garantizan calidad para segmentación."""
    thumb = ImageOps.contain(image.convert("L"), (512, 512))
    pixels = np.asarray(thumb, dtype=np.float32)
    mean_luma = float(pixels.mean())
    # Laplaciano discreto en interior; menor varianza suele sugerir desenfoque,
    # pero depende de textura de la escena y de su resolución.
    focus_proxy = 0.0
    if min(pixels.shape) >= 3:
        lap = (pixels[:-2, 1:-1] + pixels[2:, 1:-1] + pixels[1:-1, :-2]
               + pixels[1:-1, 2:] - 4 * pixels[1:-1, 1:-1])
        focus_proxy = float(lap.var())
    hints = []
    if mean_luma < 45:
        hints.append("imagen_posiblemente_oscura")
    if mean_luma > 215:
        hints.append("imagen_posiblemente_sobreexpuesta")
    if focus_proxy < 45:
        hints.append("imagen_posiblemente_borrosa_o_sin_textura")
    if min(image.size) < 320:
        hints.append("resolucion_reducida")
    return {
        "status": "possible_issue" if hints else "no_obvious_issue",
        "brightness_mean_0_255": round(mean_luma, 1),
        "sharpness_proxy_uncalibrated": round(focus_proxy, 1),
        "heuristic_flags": hints,
        "note": "Indicadores técnicos heurísticos; los umbrales no han sido validados con fotos del Chillón.",
    }


def _temporal_compare(current_mask: np.ndarray | None, previous_mask: np.ndarray | None,
                      camera_id: str | None, previous_camera_id: str | None,
                      roi_xyxy: list[int] | None) -> dict[str, Any]:
    if previous_mask is None:
        return {"status": "not_performed", "reason": "sin_mascara_anterior"}
    if current_mask is None:
        return {"status": "not_performed", "reason": "segmentacion_actual_no_disponible"}
    if not camera_id or camera_id != previous_camera_id:
        return {"status": "not_performed", "reason": "requiere_misma_camara_fija"}
    prev = np.asarray(previous_mask).astype(bool)
    curr = np.asarray(current_mask).astype(bool)
    if prev.shape != curr.shape:
        return {"status": "not_performed", "reason": "dimensiones_no_coinciden"}
    height, width = curr.shape
    if roi_xyxy is None:
        return {"status": "not_performed", "reason": "falta_region_de_referencia_roi"}
    if len(roi_xyxy) != 4:
        return {"status": "not_performed", "reason": "roi_invalida"}
    x1, y1, x2, y2 = (int(v) for v in roi_xyxy)
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        return {"status": "not_performed", "reason": "roi_fuera_de_imagen"}
    a = float(curr[y1:y2, x1:x2].mean())
    b = float(prev[y1:y2, x1:x2].mean())
    return {
        "status": "compared_unverified",
        "roi_xyxy": [x1, y1, x2, y2],
        "current_water_fraction_roi": round(a, 5),
        "previous_water_fraction_roi": round(b, 5),
        "change_fraction_points": round((a - b) * 100, 2),
        "note": "Cambio de área segmentada en una ROI, NO de nivel, caudal ni peligro. Exige encuadre fijo, registro y máscaras confiables.",
    }


def _boxes_image(image: Image.Image, boxes: list[dict[str, Any]]) -> Image.Image:
    out = image.copy()
    drawer = ImageDraw.Draw(out)
    for box in boxes:
        coords = box["bbox_xyxy"]
        code = box.get('water_mask_overlap', {}).get('status')
        color = ((0, 185, 201) if code == 'high_overlap' else
                 (248, 172, 66) if code == 'partial_overlap' else
                 (196, 196, 196))
        drawer.rectangle(coords, outline=color, width=max(2, image.width // 350))
        label = f"{box.get('candidate_id', '?')} {box['label']}"
        drawer.text((coords[0] + 2, max(0, coords[1] - 15)), label[:46], fill=color)
    return out


def _safe_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """No copiar nombres, teléfonos ni identificadores personales al informe IA."""
    allowed = {"source", "point_id", "camera_id", "captured_at", "capture_is_historical"}
    d = {k: context.get(k) for k in allowed if context and k in context}
    if d.get("source") not in {None, "citizen", "iot", "historical", "test"}:
        raise ValueError("source debe ser citizen, iot, historical o test")
    return d


def analyze_observation(
    image: Image.Image | bytes | str | Path, *,
    context: dict[str, Any] | None = None,
    model_name: str = "segformer_b0",
    checkpoint: str | None = None,
    device: str = "cpu",
    detect_objects: bool = False,
    detector: Any = None,
    water_predictor: Any = None,
    previous_mask: np.ndarray | None = None,
    previous_camera_id: str | None = None,
    roi_xyxy: list[int] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Devuelve (reporte JSON-compatible, artefactos PIL/np). No guarda ni sube nada.

    `water_predictor` y `detector` permiten tests con dobles sin descargar pesos.
    """
    started = perf_counter()
    rgb = open_image(image)
    context = _safe_context(context)
    fingerprint = hashlib.sha256(rgb.tobytes()).hexdigest()
    quality = quality_indicators(rgb)
    issues = list(quality["heuristic_flags"])
    artifacts: dict[str, Any] = {"image_original": rgb}

    water = {"status": "not_performed", "note": "No se debe interpretar ausencia de máscara como ausencia de agua."}
    water_mask = None
    try:
        prediction = (water_predictor(rgb) if water_predictor is not None else
                      predict_image(rgb, model_name=model_name, checkpoint=checkpoint, device=device))
        water_mask = np.asarray(prediction.mask, dtype=bool)
        if water_mask.shape != (rgb.height, rgb.width):
            raise ValueError("La máscara no coincide con las dimensiones de la fotografía")
        artifacts["mask"] = water_mask
        artifacts["water_overlay"] = prediction.overlay
        ratio = float(water_mask.mean())
        water = {
            "status": "predicted_nonempty" if water_mask.any() else "predicted_empty_needs_review",
            "model": prediction.report.get("model_name", model_name),
            "checkpoint": prediction.report.get("model_checkpoint", checkpoint),
            "fraction_of_image_predicted_as_water": round(ratio, 6),
            "predicted_water_pixels": int(water_mask.sum()),
            "inference_ms": prediction.report.get("inference_ms"),
            "note": "Área de imagen predicha como agua. NO equivale a porcentaje del cauce, nivel ni caudal.",
        }
        if not water_mask.any():
            issues.append("modelo_no_identifico_agua_no_significa_rio_seco")
    except Exception as exc:
        water = {"status": "error", "error_type": type(exc).__name__,
                 "note": "Falló el análisis; se mantiene la evidencia para revisión."}
        issues.append("segmentacion_no_disponible")

    objects = {"status": "not_performed", "reason": "deteccion_opcional_no_activada", "candidates": []}
    if detect_objects:
        try:
            if detector is None:
                from .object_detector import get_detector
                detector = get_detector(device=device)
            raw_candidates = detector.predict(rgb)
            combined = enrich_candidates(raw_candidates, water_mask, rgb.width, rgb.height)
            objects = {
                "status": "candidates_found" if combined['candidate_group_count'] else "no_candidates_found_not_absence",
                "model": getattr(detector, "source", "detector_de_prueba"),
                "raw_candidates": raw_candidates,  # No se destruyen los datos de origen.
                "candidates": combined['candidates'],
                "spatial_analysis": {key: value for key, value in combined.items() if key != 'candidates'},
                "note": "Detecciones tentativas: solapamiento de recuadros NO prueba obstrucción ni riesgo.",
            }
            artifacts["objects_overlay"] = _boxes_image(rgb, combined['candidates'])
            if water_mask is not None:
                artifacts["combined_overlay"] = _boxes_image(artifacts["water_overlay"], combined['candidates'])
            if raw_candidates:
                issues.append("objetos_candidatos_para_verificar")
            if combined['possible_duplicate_predictions']:
                issues.append("predicciones_superpuestas_por_confirmar")
            if not combined['water_mask_available_for_spatial_analysis'] and raw_candidates:
                issues.append("ubicacion_relativa_al_agua_no_evaluable")
        except Exception as exc:
            objects = {"status": "error", "error_type": type(exc).__name__, "candidates": []}
            issues.append("deteccion_objetos_no_disponible")

    temporal = _temporal_compare(water_mask, previous_mask,
                                 context.get("camera_id"), previous_camera_id, roi_xyxy)
    if temporal.get("status") == "compared_unverified":
        issues.append("comparacion_temporal_requiere_validacion")

    observations = []
    if water["status"] == "predicted_nonempty":
        observations.append("El modelo identificó algunas regiones de agua visible.")
    elif water["status"] == "predicted_empty_needs_review":
        observations.append("El modelo no segmentó agua; el resultado no permite concluir que el cauce esté seco.")
    else:
        observations.append("La segmentación no estuvo disponible.")
    if objects["status"] == "candidates_found":
        n_raw = len(objects['raw_candidates'])
        n_groups = len(objects['candidates'])
        observations.append(f"Se obtuvieron {n_raw} predicciones de objetos agrupadas en {n_groups} candidatos para revisión.")
        spatial = objects['spatial_analysis']
        if spatial['water_mask_available_for_spatial_analysis']:
            overlap_count = spatial['box_overlap_groups']['high_overlap']
            if overlap_count:
                observations.append(f"{overlap_count} recuadro(s) tienen solapamiento alto con la máscara de agua; NO confirma que los objetos estén sumergidos.")
        else:
            observations.append("No se pudo analizar el solapamiento de objetos con agua de forma confiable.")
    if temporal["status"] == "compared_unverified":
        observations.append("Existe una comparación descriptiva entre capturas de una cámara fija.")
    if quality["status"] == "possible_issue":
        observations.append("La imagen presenta posibles limitaciones técnicas de calidad.")

    report = {
        "schema_version": "2.1",
        "report_type": "waki_visual_observation",
        "analysis_status": "needs_review" if issues else "processed_pending_human_review",
        "input": {**context, "image_width": rgb.width, "image_height": rgb.height,
                  "image_sha256_pixels": fingerprint},
        "modules": {"image_quality": quality, "water_segmentation": water,
                    "object_candidates": objects, "temporal_comparison": temporal},
        "summary": {
            "observations": observations,
            "review_reasons": sorted(set(issues)),
            "human_review_required": True,
            "inspection_priority": None,
            "risk_level": None,
            "suggested_action": "Revisar evidencia y contrastarla con observaciones de campo.",
        },
        "processing_ms_total": round((perf_counter() - started) * 1000, 1),
        "disclaimer": "Análisis exploratorio de imagen; no es una evaluación hidrológica ni una alerta de inundación.",
    }
    return report, artifacts


def save_observation_outputs(report: dict[str, Any], artifacts: dict[str, Any], out_dir: str | Path) -> Path:
    import json
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    names: dict[str, str] = {}
    for key, value in artifacts.items():
        if key == "mask":
            filename = "mascara_agua.png"
            Image.fromarray((np.asarray(value).astype(np.uint8) * 255), mode="L").save(folder / filename)
        elif key == "image_original":
            filename = "original.jpg"
            value.save(folder / filename, quality=93)
        elif key == "water_overlay":
            filename = "segmentacion.jpg"
            value.save(folder / filename, quality=93)
        elif key == "objects_overlay":
            filename = "objetos.jpg"
            value.save(folder / filename, quality=93)
        elif key == "combined_overlay":
            filename = "analisis_combinado.jpg"
            value.save(folder / filename, quality=93)
        else:
            continue
        names[key] = filename
    report = {**report, "artifacts_relative_paths": names}
    out = folder / "reporte.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
