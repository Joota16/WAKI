"""WAKI v4: API estable imagen -> SegFormer + YOLOE multiescala + DINO -> JSON.

No infiere riesgo, caudal, nivel ni bloqueos. Todos los hallazgos son revisables.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from .inference import Prediction, mask_overlay
from .visual_report import analyze_observation, open_image, save_observation_outputs
from .hybrid_fusion import fuse_candidates, build_review_regions
from .yoloe_multiscale import DEFAULT_CLASSES, extract, make_tiles


class YoloeMultiscaleAdapter:
    """Se instancia una vez por proceso. Mantiene las predicciones brutas."""
    source = 'yoloe-26s-seg.pt'

    def __init__(self, device: str = '0', conf: float = .20, tile: int = 480,
                 overlap: float = .25, imgsz: int = 768,
                 classes: list[str] | None = None, weights: str = 'yoloe-26s-seg.pt'):
        from ultralytics import YOLOE
        self.device = '0' if device in ('cuda', 'cuda:0') else device
        self.conf, self.tile, self.overlap, self.imgsz = conf, tile, overlap, imgsz
        self.source = weights
        self.classes = classes or DEFAULT_CLASSES
        self.model = YOLOE(weights)
        self.model.set_classes(self.classes)
        self.last_runtime_ms = None

    def predict(self, image: Image.Image) -> list[dict]:
        import cv2
        rgb = np.asarray(image.convert('RGB'))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        h, w = bgr.shape[:2]
        start = perf_counter()
        observations = []
        pred = self.model.predict(bgr, device=self.device, conf=self.conf,
                                  imgsz=self.imgsz, verbose=False)[0]
        boxes, _ = extract(pred, (0, 0), w, h, w, h, 'full', self.conf, .45)
        observations.extend(boxes)
        for i, (x1, y1, x2, y2) in enumerate(make_tiles(w, h, self.tile, self.overlap), 1):
            if (x1, y1, x2, y2) == (0, 0, w, h):
                continue
            crop = bgr[y1:y2, x1:x2]
            pred = self.model.predict(crop, device=self.device, conf=self.conf,
                                      imgsz=self.imgsz, verbose=False)[0]
            boxes, _ = extract(pred, (x1, y1), w, h, x2-x1, y2-y1,
                               f'tile_{i:02d}', self.conf, .80)
            observations.extend(boxes)
        self.last_runtime_ms = round((perf_counter() - start) * 1000, 1)
        # Pre-retención de polígonos para cálculo espacial en la fusión
        for item in observations:
            if item.get('_polygon'):
                item['polygon_xy'] = item.pop('_polygon')
            else:
                item.pop('_polygon', None)
        return observations


class DinoAdapter:
    source = 'IDEA-Research/grounding-dino-tiny'
    def __init__(self, device: str = 'cuda'):
        from .object_detector import get_detector
        self.detector = get_detector(device=device)
        self.last_runtime_ms = None

    def predict(self, image: Image.Image) -> list[dict]:
        start = perf_counter()
        output = self.detector.predict(image)
        self.last_runtime_ms = round((perf_counter() - start) * 1000, 1)
        return output


@lru_cache(maxsize=2)
def get_yoloe(device: str = '0'):
    return YoloeMultiscaleAdapter(device=device)


@lru_cache(maxsize=2)
def get_dino(device: str = 'cuda'):
    return DinoAdapter(device=device)


def _draw_boxes(image: Image.Image, candidates: list[dict]) -> Image.Image:
    out = image.copy()
    painter = ImageDraw.Draw(out)
    palette = ['#f2a94a', '#16a7be', '#b482ee', '#e57969', '#73bb8e']
    for i, c in enumerate(candidates):
        x1, y1, x2, y2 = c['bbox_xyxy']
        color = palette[i % len(palette)]
        painter.rectangle([x1, y1, x2-1, y2-1], outline=color, width=3)
        # Mostrar índice y fuente(s); labels extensas quedan en el reporte para evitar solapamiento visual
        badge = c.get('candidate_id', f'OBJ-{i+1:03d}')
        text_y = max(0, y1 - 16)
        tw = 78
        painter.rectangle([x1, text_y, x1+tw, text_y+15], fill=color)
        painter.text((x1+3, text_y+1), badge, fill='black')
    return out


def _precomputed_predictor(mask: np.ndarray, source: str = 'precomputed_mask_for_replay'):
    def predict(image: Image.Image):
        if mask.shape != (image.height, image.width):
            raise ValueError('Máscara almacenada no coincide con la foto')
        return Prediction(mask=mask.astype(bool), overlay=mask_overlay(image, mask.astype(bool)),
                          report={'model_name': source, 'model_checkpoint': None,
                                  'inference_ms': None})
    return predict


def analyze_hybrid_observation(
    image: Image.Image | bytes | str | Path, *,
    context: dict | None = None,
    checkpoint: str | None = None,
    device: str = 'cuda',
    use_yoloe: bool = True, use_dino: bool = True,
    yoloe_detector: Any = None, dino_detector: Any = None,
    water_predictor: Any = None,
    precomputed_water_mask: np.ndarray | None = None,
    replay_yoloe: list[dict] | None = None,
    replay_dino: list[dict] | None = None,
    previous_mask: np.ndarray | None = None,
    previous_camera_id: str | None = None,
    roi_xyxy: list[int] | None = None,
) -> tuple[dict, dict]:
    """Devuelve (reporte JSON-serializable, artefactos PIL/numpy).

    replay_* permite pruebas sin cargar pesos; NO es una inferencia nueva.
    Si falla un detector, el otro y SegFormer siguen disponibles.
    """
    started = perf_counter()
    rgb = open_image(image)
    replay_mode = replay_yoloe is not None or replay_dino is not None or precomputed_water_mask is not None
    if precomputed_water_mask is not None:
        water_predictor = _precomputed_predictor(np.asarray(precomputed_water_mask))
    report, artifacts = analyze_observation(
        rgb, context=context, model_name='segformer_b0',
        checkpoint=checkpoint, device=device, detect_objects=False,
        water_predictor=water_predictor,
        previous_mask=previous_mask, previous_camera_id=previous_camera_id, roi_xyxy=roi_xyxy)
    mask = artifacts.get('mask')
    raw_by_model: dict[str, list[dict]] = {}
    statuses = {}
    for name, enabled, detector, replay in (
        ('yoloe_multiscale', use_yoloe, yoloe_detector, replay_yoloe),
        ('grounding_dino', use_dino, dino_detector, replay_dino),
    ):
        if not enabled:
            statuses[name] = {'status': 'disabled'}
            continue
        try:
            if replay is not None:
                raw = replay
                model_label = 'saved_predictions_for_replay'
                runtime = None
            else:
                if detector is None:
                    detector = get_yoloe(device=device) if name == 'yoloe_multiscale' else get_dino(device=device)
                raw = detector.predict(rgb)
                model_label = getattr(detector, 'source', name)
                runtime = getattr(detector, 'last_runtime_ms', None)
            if not isinstance(raw, list):
                raise ValueError(f'{name} devolvió una salida que no es lista')
            raw_by_model[name] = raw
            statuses[name] = {'status': 'processed', 'model': model_label,
                              'raw_candidate_count': len(raw), 'runtime_ms': runtime,
                              'replayed': replay is not None}
        except Exception as exc:
            raw_by_model[name] = []
            statuses[name] = {'status': 'error', 'error_type': type(exc).__name__,
                              'note': 'Detector no disponible. No equivale a ausencia de objetos.'}
    fusion = fuse_candidates(raw_by_model, rgb.width, rgb.height, water_mask=mask)
    review_regions = build_review_regions(fusion['candidates'], rgb.width, rgb.height)
    report['schema_version'] = '4.0'
    report['modules']['object_candidates'] = {
        'status': fusion['status'] if any(s['status'] == 'processed' for s in statuses.values())
                  else 'not_available',
        'model_status': statuses,
        'candidates': fusion['candidates'],
        'fusion': {k: v for k, v in fusion.items() if k != 'candidates'},
        'review_regions': review_regions,
        'note': 'Hipótesis no verificadas; nunca se calcula riesgo mediante conteos.'}
    report['summary']['human_review_required'] = True
    report['summary']['risk_level'] = None
    report['summary']['inspection_priority'] = None
    report['summary']['observations'] = [o for o in report['summary']['observations']
                                          if 'deteccion' not in o.lower()]
    if fusion['candidates']:
        report['summary']['observations'].append(
            f"Se registran {len(fusion['candidates'])} candidatos en {len(review_regions)} zonas para revisión humana; no son objetos confirmados.")
        report['summary']['review_reasons'] = sorted(set(report['summary']['review_reasons'] +
                                                        ['materiales_candidatos_no_verificados']))
    elif any(s['status'] == 'error' for s in statuses.values()):
        report['summary']['review_reasons'] = sorted(set(report['summary']['review_reasons'] +
                                                        ['detector_parcialmente_no_disponible']))
    report['summary']['candidate_count'] = len(fusion['candidates'])
    report['summary']['review_zone_count'] = len(review_regions)
    report['analysis_status'] = 'needs_review'
    report['analysis_mode'] = 'offline_replay' if replay_mode else 'live_models'
    report['processing_ms_total'] = round((perf_counter()-started) * 1000, 1)
    report['limitations'] = [
        'Los modelos no estiman peligro, obstrucción hidráulica, caudal ni nivel del río.',
        'La coincidencia entre modelos o con una máscara de agua no confirma la identidad del material.',
        'La ausencia de candidatos no es prueba de ausencia de residuos.',
        'Las puntuaciones de dos arquitecturas no son comparables ni probabilidades calibradas.',
    ]
    regions_for_drawing = [{'bbox_xyxy': x['bbox_xyxy'], 'candidate_id': x['region_id']} for x in review_regions]
    artifacts['objects_overlay'] = _draw_boxes(rgb, regions_for_drawing)
    artifacts['combined_overlay'] = _draw_boxes(artifacts.get('water_overlay', rgb), regions_for_drawing)
    return report, artifacts


def save_hybrid_outputs(report: dict, artifacts: dict, out_dir: str | Path) -> Path:
    """Conserva contrato v2.1: reporte.json + original.jpg + segmentacion.jpg etc."""
    return save_observation_outputs(report, artifacts, out_dir)
