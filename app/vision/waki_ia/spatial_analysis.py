"""Posprocesamiento conservador de candidatos Grounding DINO y máscara SegFormer.

No evalúa riesgo, bloqueo físico ni nivel hidráulico. Los recuadros incluyen
fondo, por lo que la intersección de un recuadro NO es la ubicación exacta
ni una máscara del objeto.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np


def intersection_over_union(a: list[int], b: list[int]) -> float:
    """IoU de cajas xyxy con coordenadas extremas exclusivas."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    intersection = max(0, min(ax2, bx2) - max(ax1, bx1)) * max(0, min(ay2, by2) - max(ay1, by1))
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    denom = area_a + area_b - intersection
    return intersection / denom if denom > 0 else 0.0


def _normalize(raw: dict[str, Any], width: int, height: int, index: int) -> dict[str, Any] | None:
    """Descarta cajas inválidas, recorta a la imagen y preserva origen."""
    try:
        bounds = raw['bbox_xyxy']
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
            return None
        coords = [int(round(float(x))) for x in bounds]
        x1, y1, x2, y2 = coords
        clipped = [max(0, min(width, x1)), max(0, min(height, y1)),
                   max(0, min(width, x2)), max(0, min(height, y2))]
        if clipped[0] >= clipped[2] or clipped[1] >= clipped[3]:
            return None
        value = float(raw.get('score_uncalibrated', 0.0))
        if not np.isfinite(value):
            return None
        normalized = deepcopy(raw)
        normalized['bbox_xyxy'] = clipped
        normalized['score_uncalibrated'] = value
        normalized['_input_index'] = index
        normalized['label'] = str(raw.get('label') or 'objeto_sin_etiqueta')
        return normalized
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def enrich_candidates(
    raw_candidates: list[dict[str, Any]],
    water_mask: np.ndarray | None,
    image_width: int,
    image_height: int,
    *,
    duplicate_iou_threshold: float = 0.85,
) -> dict[str, Any]:
    """Agrupa recuadros casi idénticos y calcula su solapamiento con el agua.

    Los labels alternativos permanecen en el JSON; no se asegura que sean
    el mismo objeto. Sin máscara válida NO se calcula ubicación relativa.
    """
    if image_width <= 0 or image_height <= 0:
        raise ValueError('Dimensiones de imagen inválidas')
    if not 0 < duplicate_iou_threshold <= 1:
        raise ValueError('El umbral IoU debe estar entre cero y uno')
    mask = None
    mask_reason = 'sin_mascara_de_agua'
    if water_mask is not None:
        arr = np.asarray(water_mask)
        if arr.shape != (image_height, image_width):
            mask_reason = 'dimensiones_de_mascara_incompatibles'
        elif not np.any(arr):
            mask_reason = 'mascara_sin_agua_predicha_no_concluyente'
        else:
            mask = arr.astype(bool)
            mask_reason = None

    normalized = [c for i, r in enumerate(raw_candidates)
                  if (c := _normalize(r, image_width, image_height, i)) is not None]
    normalized.sort(key=lambda item: (-item['score_uncalibrated'], item['_input_index']))
    retained: list[dict[str, Any]] = []
    for candidate in normalized:
        group = None
        for item in retained:
            if intersection_over_union(candidate['bbox_xyxy'], item['bbox_xyxy']) >= duplicate_iou_threshold:
                group = item
                break
        if group is None:
            item = deepcopy(candidate)
            item['candidate_id'] = f'OBJ-{len(retained)+1:03d}'
            item['alternate_predictions'] = []
            item['raw_prediction_indices'] = [candidate['_input_index']]
            retained.append(item)
        else:
            group['alternate_predictions'].append({
                'label': candidate['label'],
                'score_uncalibrated': round(candidate['score_uncalibrated'], 4),
                'bbox_xyxy': candidate['bbox_xyxy'],
                'raw_prediction_index': candidate['_input_index'],
                'iou_with_retained_box': round(intersection_over_union(candidate['bbox_xyxy'], group['bbox_xyxy']), 4),
            })
            group['raw_prediction_indices'].append(candidate['_input_index'])

    categories = {'high_overlap': 0, 'partial_overlap': 0, 'low_overlap': 0, 'not_evaluable': 0}
    for candidate in retained:
        candidate.pop('_input_index', None)
        candidate['duplicate_group_size'] = len(candidate['raw_prediction_indices'])
        x1, y1, x2, y2 = candidate['bbox_xyxy']
        bbox_ratio = (x2-x1) * (y2-y1) / (image_width * image_height)
        if mask is None:
            code = 'not_evaluable'
            fraction = None
        else:
            fraction = float(mask[y1:y2, x1:x2].mean())
            # Estas etiquetas son sobre el RECUADRO, no sobre el objeto.
            code = ('high_overlap' if fraction >= 0.65 else
                    'partial_overlap' if fraction >= 0.20 else 'low_overlap')
        categories[code] += 1
        candidate['water_mask_overlap'] = {
            'status': code,
            'fraction_of_bbox_predicted_as_water': None if fraction is None else round(fraction, 4),
            'bbox_fraction_of_image': round(bbox_ratio, 4),
            'large_box_warning': bbox_ratio >= 0.08,
            'reason_if_unavailable': mask_reason if mask is None else None,
            'note': ('Solapamiento de la CAJA con máscara no validada; el recuadro contiene fondo. '
                     'NO demuestra que el objeto esté sumergido ni que obstruya el flujo.'),
        }

    return {
        'status': 'analyzed_unverified' if retained else 'no_valid_candidates',
        'raw_candidate_count': len(raw_candidates),
        'valid_candidate_count': len(normalized),
        'candidate_group_count': len(retained),
        'possible_duplicate_predictions': len(normalized) - len(retained),
        'discarded_invalid_boxes': len(raw_candidates) - len(normalized),
        'duplicate_iou_threshold': duplicate_iou_threshold,
        'water_mask_available_for_spatial_analysis': mask is not None,
        'mask_issue': mask_reason,
        'box_overlap_groups': categories,
        'candidates': retained,
        'note': ('Grupos de predicciones no verificados. Una coincidencia entre cajas NO certifica identidad; '
                 'el solapamiento con agua es de píxeles dentro del recuadro, NO localiza el objeto de forma exacta.'),
    }
