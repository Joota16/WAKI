"""WAKI v4: agrupación CONSERVADORA de detecciones, nunca confirmación de riesgo.

La IoU y la contención son heurísticas geométricas, no prueban identidad.
Las puntuaciones entre modelos no se comparan entre sí ni se promedian.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any
import numpy as np

CATEGORIES = {
    "tire": ("residuo_voluminoso", "Neumático"),
    "plastic bottle": ("residuo_plastico", "Botella de plástico"),
    "bottle": ("residuo_plastico", "Botella (sin verificar)"),
    "plastic bag": ("residuo_plastico", "Bolsa plástica"),
    "garbage bag": ("residuo_plastico", "Bolsa de basura"),
    "plastic container": ("residuo_plastico", "Envase plástico"),
    "foam packaging": ("residuo_embalaje", "Embalaje de espuma"),
    "cardboard": ("residuo_embalaje", "Cartón"),
    "discarded clothing": ("residuo_textil", "Textil"),
    "tree branch": ("madera_vegetal", "Ramas"),
    "tree branches": ("madera_vegetal", "Ramas"),
    "fallen tree trunk": ("madera_vegetal", "Tronco"),
    "wood log": ("madera_vegetal", "Tronco / madera"),
    "tree trunk": ("madera_vegetal", "Tronco"),
    "log": ("madera_vegetal", "Tronco"),
    "branches": ("madera_vegetal", "Ramas"),
    "concrete block": ("escombro_construccion", "Bloque de concreto"),
    "large rock": ("roca_natural", "Roca grande"),
    "rock": ("roca_natural", "Roca"),
    "pile of garbage": ("acumulacion_no_verificada", "Posible acumulación de basura"),
    "pile of mixed debris": ("acumulacion_no_verificada", "Posible acumulación mixta"),
}


def rect_iou(a: list[int], b: list[int]) -> float:
    intr, ar_a, ar_b = _areas(a, b)
    denom = ar_a + ar_b - intr
    return intr / denom if denom else 0.0


def _areas(a, b):
    x1, y1, x2, y2 = a
    u1, v1, u2, v2 = b
    inter = max(0, min(x2, u2)-max(x1, u1)) * max(0, min(y2, v2)-max(y1, v1))
    return inter, max(0, x2-x1)*max(0, y2-y1), max(0, u2-u1)*max(0, v2-v1)


def _normalize(item: dict, model: str, width: int, height: int) -> dict | None:
    try:
        box = item.get("bbox_xyxy") or item.get("box")
        if len(box) != 4:
            return None
        vals = [float(v) for v in box]
        if not all(math.isfinite(v) for v in vals):
            return None
        x1, y1, x2, y2 = vals
        box = [max(0, min(width, round(x1))), max(0, min(height, round(y1))),
               max(0, min(width, round(x2))), max(0, min(height, round(y2)))]
        if box[0] >= box[2] or box[1] >= box[3]:
            return None
        score = float(item.get('score_uncalibrated', item.get('score', 0)))
        if not math.isfinite(score):
            return None
        label = str(item.get('label_en') or item.get('label') or 'objeto_sin_identificar').strip().lower()
        # No confiar en descripciones genéricas devueltas por DINO como categoría de material
        category, translated = CATEGORIES.get(label, ('sin_categoria_confirmada', 'Objeto por verificar'))
        return {
            'source_model': model, 'raw_label': label, 'proposed_label_es': translated,
            'material_category_proposed': category, 'score_uncalibrated': round(score, 4),
            'bbox_xyxy': box, 'source_region': item.get('source', 'full'),
            'polygon_xy': item.get('polygon_xy') or item.get('mask_polygon_xy'),
        }
    except (TypeError, ValueError, KeyError, OverflowError):
        return None


def _same_region(a: dict, b: dict, same_iou: float, cross_iou: float) -> bool:
    ia = rect_iou(a['bbox_xyxy'], b['bbox_xyxy'])
    if a['source_model'] == b['source_model'] and a['raw_label'] == b['raw_label']:
        return ia >= same_iou
    if ia >= cross_iou:
        return True
    # Contención con tamaños parecidos; no fusionar una caja pequeña dentro de una caja enorme
    intersection, area_a, area_b = _areas(a['bbox_xyxy'], b['bbox_xyxy'])
    small, large = min(area_a, area_b), max(area_a, area_b)
    return bool(small and intersection / small >= .93 and small / large >= .58)


def _overlap_with_water(item: dict, mask: np.ndarray | None) -> dict:
    if mask is None or not mask.any():
        return {'status': 'not_evaluable', 'fraction': None,
                'basis': None, 'note': 'Sin máscara de agua usable; NO significa que el cauce esté seco.'}
    x1, y1, x2, y2 = item['bbox_xyxy']
    patch = mask[y1:y2, x1:x2]
    polygon = item.get('polygon_xy')
    if polygon:
        try:
            import cv2
            shape = np.asarray(polygon, dtype=np.float64)
            if shape.ndim == 2 and shape.shape[0] >= 3 and shape.shape[1] == 2:
                local = np.round(shape - [x1, y1]).astype(np.int32)
                obj = np.zeros((y2-y1, x2-x1), dtype=np.uint8)
                cv2.fillPoly(obj, [local], 1)
                if obj.sum():
                    fraction = float(np.logical_and(patch, obj > 0).sum() / obj.sum())
                    return {'status': 'overlap_unverified', 'fraction': round(fraction, 4),
                            'basis': 'predicted_instance_polygon',
                            'note': 'Máscara predicha, no validada; NO demuestra bloqueo de agua.'}
        except (ValueError, TypeError, ImportError):
            pass
    fraction = float(patch.mean()) if patch.size else None
    return {'status': 'overlap_unverified', 'fraction': round(fraction, 4) if fraction is not None else None,
            'basis': 'bounding_box_includes_background',
            'note': 'Solapamiento del RECUADRO con la máscara de agua, no del objeto exacto.'}


def fuse_candidates(raw_by_model: dict[str, list[dict]], width: int, height: int,
                    water_mask: np.ndarray | None = None, same_iou: float = .48,
                    cross_iou: float = .78) -> dict[str, Any]:
    """Fusiona solamente detecciones muy coincidentes, conservando todas las hipótesis.

    `same_iou` agrupa duplicados de un mismo modelo/clase entre tiles.
    `cross_iou` enlaza hipótesis cruzadas solo si las cajas casi coinciden.
    """
    if width <= 0 or height <= 0 or not (0 < same_iou <= 1 and 0 < cross_iou <= 1):
        raise ValueError('Dimensiones/umbrales inválidos')
    if water_mask is not None and np.asarray(water_mask).shape != (height, width):
        raise ValueError('La máscara de agua no coincide con la imagen')
    valid = []
    counts = {}
    for model, predictions in raw_by_model.items():
        counts[model] = len(predictions)
        for raw in predictions:
            normalized = _normalize(raw, model, width, height)
            if normalized is not None:
                valid.append(normalized)
    # No privilegiar scores entre modelos: ordenar solo dentro de la misma categoría;
    # usar modelo+coordenadas para asignación determinista.
    valid.sort(key=lambda x: (x['source_model'], -x['score_uncalibrated'], tuple(x['bbox_xyxy'])))
    groups: list[list[dict]] = []
    for c in valid:
        matched = None
        for group in groups:
            if any(_same_region(c, old, same_iou, cross_iou) for old in group):
                # No usar 'puentes' transitivos de cajas distantes para agrupar regiones distintas
                if _same_region(c, group[0], same_iou, cross_iou):
                    matched = group
                    break
        if matched is None:
            groups.append([c])
        else:
            matched.append(c)

    candidates = []
    mask = np.asarray(water_mask, dtype=bool) if water_mask is not None else None
    for idx, group in enumerate(groups, 1):
        # Priorizar segmentación YOLOE para el dibujo/espacial, no su puntuación vs DINO
        yolo = [x for x in group if x['source_model'] == 'yoloe_multiscale']
        rep = max(yolo or group, key=lambda x: x['score_uncalibrated'])
        hypotheses = [{k: v for k, v in x.items() if k != 'polygon_xy'} for x in group]
        labels = sorted(set(x['raw_label'] for x in group))
        sources = sorted(set(x['source_model'] for x in group))
        has_conflict = len({x['material_category_proposed'] for x in group}) > 1
        overlap = _overlap_with_water(rep, mask)
        box = rep['bbox_xyxy']
        box_frac = (box[2]-box[0])*(box[3]-box[1]) / (width * height)
        candidates.append({
            'candidate_id': f'OBJ-{idx:03d}', 'label': rep['raw_label'],
            'label_es': rep['proposed_label_es'],
            'category_proposed': rep['material_category_proposed'],
            'bbox_xyxy': box, 'bbox_fraction_image': round(box_frac, 4),
            'large_box_warning': box_frac >= .12,
            'source_models': sources, 'source_model_count': len(sources),
            'label_conflict': has_conflict,
            'alternate_labels': labels, 'hypotheses': hypotheses,
            'raw_prediction_count': len(group),
            'water_relation': overlap,
            'verification_status': 'pending_human_review',
            'evidence_note': ('Coincidencia entre modelos NO implica confirmación;'
                              ' la ausencia de candidatos NO demuestra ausencia de material.'),
        })
    return {
        'status': 'candidates_found' if candidates else 'no_candidates_detected_not_absence',
        'raw_prediction_count': sum(counts.values()),
        'valid_prediction_count': len(valid), 'discarded_invalid_boxes': sum(counts.values()) - len(valid),
        'grouped_candidate_count': len(candidates), 'merged_prediction_count': len(valid) - len(candidates),
        'labels_in_conflict': sum(c['label_conflict'] for c in candidates),
        'raw_counts_by_model': counts, 'candidates': candidates,
        'review_required': True,
        'method_note': ('Agrupación geométrica conservadora; no se suman puntuaciones entre modelos. '
                        'Ninguna detección es prueba de obstrucción o peligro.'),
    }


def build_review_regions(candidates: list[dict], width: int, height: int) -> list[dict]:
    """Agrupa candidatos próximos en REGIONES VISUALES, no como un solo objeto.

    Un recuadro puede contener múltiples objetos; este agrupamiento reduce saturación
    de la imagen, mientras `candidates[]` mantiene TODOS los candidatos individuales.
    """
    groups: list[list[dict]] = []
    for c in sorted(candidates, key=lambda z: -z['bbox_fraction_image']):
        matched = None
        for group in groups:
            # ancla: no usar transitividad para combinar toda la ribera
            a, b = c['bbox_xyxy'], group[0]['bbox_xyxy']
            intr, ar_a, ar_b = _areas(a, b)
            contain = intr / min(ar_a, ar_b) if min(ar_a, ar_b) else 0
            if rect_iou(a,b) >= .40 or contain >= .85:
                matched = group
                break
        if matched is None:
            groups.append([c])
        else:
            matched.append(c)
    regions = []
    for i, g in enumerate(groups, 1):
        x1 = min(z['bbox_xyxy'][0] for z in g)
        y1 = min(z['bbox_xyxy'][1] for z in g)
        x2 = max(z['bbox_xyxy'][2] for z in g)
        y2 = max(z['bbox_xyxy'][3] for z in g)
        rid = f'ZONA-{i:03d}'
        for c in g:
            c['review_region_id'] = rid
        regions.append({'region_id': rid, 'bbox_xyxy': [x1,y1,x2,y2],
                        'candidate_ids':[z['candidate_id'] for z in g],
                        'candidate_count': len(g),
                        'labels_proposed': sorted({lab for z in g for lab in z['alternate_labels']}),
                        'note': 'Una zona de revisión puede contener VARIOS objetos; no es una detección única.'})
    return regions
