"""WAKI: prueba experimental de detección de materiales por regiones con YOLOE.

Ejecución (PowerShell):
 python scripts/detectar_multiescala.py "C:\\Users\\Jhunior\\Downloads\\foto_de_rio.jpg" --device 0 --out outputs\\demo_multiescala

El resultado son *candidatos visuales*, no obstrucciones ni riesgos confirmados.
Requiere ultralytics, opencv-python y numpy. No entrena un modelo.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

# Evitar términos genéricos como "pile", "debris" o "garbage" en esta prueba:
# en WAKI daban falsos positivos muy grandes.
DEFAULT_CLASSES = [
    "tire", "plastic bottle", "plastic bag", "tree branch",
    "wood log", "concrete block", "foam packaging", "plastic container",
    "cardboard", "large rock", "discarded clothing",
]
SPANISH = {
    "tire": "Neumático", "plastic bottle": "Botella", "plastic bag": "Bolsa",
    "tree branch": "Ramas", "wood log": "Tronco", "concrete block": "Bloque de concreto",
    "foam packaging": "Envase de espuma", "plastic container": "Envase plástico",
    "cardboard": "Cartón", "large rock": "Roca grande",
    "discarded clothing": "Textil",
}


def positions(length: int, tile: int, overlap: float) -> list[int]:
    """Cubre la dimensión y coloca la última ventana contra el borde."""
    if length <= tile:
        return [0]
    step = max(1, int(round(tile * (1.0 - overlap))))
    p = list(range(0, length - tile + 1, step))
    end = length - tile
    if p[-1] != end:
        p.append(end)
    return p


def make_tiles(w: int, h: int, tile: int, overlap: float):
    tw, th = min(tile, w), min(tile, h)
    result = [(x, y, x + tw, y + th) for y in positions(h, th, overlap)
              for x in positions(w, tw, overlap)]
    return result


def iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intr = max(0, x2 - x1) * max(0, y2 - y1)
    aa = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    bb = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    return intr / (aa + bb - intr) if aa + bb - intr else 0.0


def merge_nms(items: list[dict], same_class_iou: float = .48, cross_class_iou: float = .82):
    """Elimina duplicados fuertes entre recortes; no garantiza identidad de objeto."""
    kept = []
    for item in sorted(items, key=lambda x: x['score'], reverse=True):
        duplicate = False
        for prior in kept:
            threshold = same_class_iou if item['label_en'] == prior['label_en'] else cross_class_iou
            if iou(item['bbox_xyxy'], prior['bbox_xyxy']) >= threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(item)
    return kept


def extract(result, offset: tuple[int, int], imgw: int, imgh: int,
            crop_w: int, crop_h: int, source: str, conf: float,
            max_area: float):
    found, rejected = [], 0
    if result.boxes is None:
        return found, rejected
    coords = result.boxes.xyxy.cpu().numpy()
    scores = result.boxes.conf.cpu().numpy()
    classes = result.boxes.cls.cpu().numpy().astype(int)
    polygons = result.masks.xy if result.masks is not None else []
    for idx, (coords_i, score, cls_i) in enumerate(zip(coords, scores, classes)):
        if score < conf:
            continue
        local_x1, local_y1, local_x2, local_y2 = (float(v) for v in coords_i)
        if local_x2 <= local_x1 or local_y2 <= local_y1:
            continue
        frac_crop = ((local_x2-local_x1)*(local_y2-local_y1)) / (crop_w * crop_h)
        if frac_crop > max_area:
            rejected += 1
            continue
        ox, oy = offset
        x1 = max(0, min(imgw, round(local_x1 + ox)))
        y1 = max(0, min(imgh, round(local_y1 + oy)))
        x2 = max(0, min(imgw, round(local_x2 + ox)))
        y2 = max(0, min(imgh, round(local_y2 + oy)))
        if x2 <= x1 or y2 <= y1:
            continue
        name = result.names.get(int(cls_i), f'class_{cls_i}')
        poly = None
        if idx < len(polygons) and len(polygons[idx]) >= 3:
            pts = np.asarray(polygons[idx], np.float32)
            pts[:, 0] += ox
            pts[:, 1] += oy
            poly = pts.astype(np.int32).tolist()
        found.append({
            'label_en': str(name), 'label_es': SPANISH.get(name, str(name)),
            'score': float(score), 'bbox_xyxy': [x1, y1, x2, y2],
            'bbox_fraction_of_image': round((x2-x1)*(y2-y1)/(imgw*imgh), 5),
            'source': source, '_polygon': poly,
        })
    return found, rejected


def water_relation(item, water_mask):
    if water_mask is None:
        return {'status': 'not_evaluated', 'reason': 'no_water_mask'}
    h, w = water_mask.shape
    x1, y1, x2, y2 = item['bbox_xyxy']
    polygon = item.get('_polygon')
    if polygon:
        local = np.asarray(polygon, np.int32) - np.asarray([x1, y1], np.int32)
        region = np.zeros((y2-y1, x2-x1), dtype=np.uint8)
        cv2.fillPoly(region, [local], 1)
        denom = int(region.sum())
        if denom:
            within = (water_mask[y1:y2, x1:x2] & (region > 0)).sum()
            return {'status': 'mask_overlap_unverified',
                    'fraction_in_water_mask': round(float(within / denom), 4),
                    'basis': 'predicted_object_mask'}
    crop = water_mask[y1:y2, x1:x2]
    return {'status': 'box_overlap_unverified',
            'fraction_in_water_mask': round(float(crop.mean()), 4) if crop.size else None,
            'basis': 'bounding_box_not_exact_object'}


def main():
    parser = argparse.ArgumentParser(description='WAKI: inferencia YOLOE multiescala para materiales')
    parser.add_argument('imagen')
    parser.add_argument('--out', default='outputs/waki_multiescala')
    parser.add_argument('--model', default='yoloe-26s-seg.pt')
    parser.add_argument('--device', default='0')
    parser.add_argument('--conf', type=float, default=0.20)
    parser.add_argument('--imgsz', type=int, default=768)
    parser.add_argument('--tile', type=int, default=480)
    parser.add_argument('--overlap', type=float, default=0.25)
    parser.add_argument('--max-area-full', type=float, default=0.45)
    parser.add_argument('--max-area-tile', type=float, default=0.80)
    parser.add_argument('--water-mask', default=None,
                        help='PNG máscara binaria de agua 0/1 o 0/255 con mismas dimensiones; opcional')
    parser.add_argument('--classes', default=','.join(DEFAULT_CLASSES))
    args = parser.parse_args()
    if not (0 < args.conf < 1 and 0 <= args.overlap < 0.9 and args.tile > 100):
        parser.error('conf, overlap o tile fuera de rango')
    path = Path(args.imagen)
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        parser.error(f'No se puede abrir imagen: {path}')
    H, W = img.shape[:2]
    classes = [c.strip() for c in args.classes.split(',') if c.strip()]
    if not classes:
        parser.error('Lista de clases vacía')
    water = None
    if args.water_mask:
        mask = cv2.imread(str(args.water_mask), cv2.IMREAD_GRAYSCALE)
        if mask is None or mask.shape != (H, W):
            parser.error('La máscara de agua debe existir y tener las dimensiones de la foto')
        water = mask > 0
    from ultralytics import YOLOE
    model = YOLOE(args.model)
    model.set_classes(classes)
    t0 = time.perf_counter()
    raw, discarded = [], 0
    r = model.predict(img, device=args.device, conf=args.conf,
                      imgsz=args.imgsz, verbose=False)[0]
    detections, reject = extract(r, (0, 0), W, H, W, H, 'full', args.conf, args.max_area_full)
    raw.extend(detections)
    discarded += reject
    tiles = make_tiles(W, H, args.tile, args.overlap)
    for j, (x1, y1, x2, y2) in enumerate(tiles, 1):
        if x1 == 0 and y1 == 0 and x2 == W and y2 == H:
            continue
        crop = img[y1:y2, x1:x2]
        r = model.predict(crop, device=args.device, conf=args.conf,
                          imgsz=args.imgsz, verbose=False)[0]
        detections, reject = extract(r, (x1, y1), W, H, x2-x1, y2-y1,
                                     f'tile_{j:02d}', args.conf, args.max_area_tile)
        raw.extend(detections)
        discarded += reject
    elapsed = round(1000 * (time.perf_counter() - t0), 1)
    kept = merge_nms(raw)
    for k, item in enumerate(kept, 1):
        item['id'] = f'OBJ-{k:03d}'
        item['water_relation'] = water_relation(item, water)
        item['requires_human_review'] = True

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    overlay = img.copy()
    colors = [(25, 175, 244), (47, 191, 120), (245, 124, 58),
              (159, 103, 230), (33, 204, 211)]  # BGR
    for i, d in enumerate(kept):
        col = colors[i % len(colors)]
        poly = d.get('_polygon')
        if poly and len(poly) >= 3:
            pts = np.asarray(poly, dtype=np.int32).reshape(-1, 1, 2)
            layer = overlay.copy()
            cv2.fillPoly(layer, [pts], col)
            overlay = cv2.addWeighted(layer, .26, overlay, .74, 0)
        x1, y1, x2, y2 = d['bbox_xyxy']
        cv2.rectangle(overlay, (x1, y1), (x2, y2), col, 2)
        label = f"{d['id']} {d['label_es']} {d['score']:.2f}"
        label_y = max(16, y1 - 6)
        cv2.putText(overlay, label, (x1 + 2, label_y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.47, (15, 15, 15), 3, cv2.LINE_AA)
        cv2.putText(overlay, label, (x1 + 2, label_y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.47, col, 1, cv2.LINE_AA)

    visual = output_dir / 'objetos_multiescala.jpg'
    cv2.imwrite(str(visual), overlay)
    output = {
        'schema_version': 'waki-materials-experimental-v3',
        'status': 'candidates_found' if kept else 'no_candidates_detected',
        'model': args.model, 'pretrained': True,
        'image_name': path.name, 'dimensions': [W, H], 'device': args.device,
        'classes_queried': classes, 'mode': 'full_plus_overlapping_tiles',
        'tile_size': args.tile, 'tile_overlap': args.overlap,
        'num_tiles': len(tiles), 'conf_threshold_experimental': args.conf,
        'predictions_before_dedup': len(raw), 'candidates_after_dedup': len(kept),
        'rejected_large_boxes': discarded, 'inference_ms_total': elapsed,
        'candidates': [{k: v for k, v in item.items() if not k.startswith('_')}
                       for item in kept],
        'visualization': visual.name,
        'human_review_required': True, 'risk_level': None,
        'notes': [
            'Las puntuaciones no están calibradas; no son probabilidades de verdad.',
            'El solapamiento de las máscaras es preliminar; no demuestra obstrucción.',
            'Una foto sin candidatos no significa que no haya residuos.',
            'La detección por recortes aumenta el coste y puede generar falsos positivos.',
        ],
    }
    report = output_dir / 'reporte_materiales_multiescala.json'
    report.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Candidatos antes/después de fusionar: {len(raw)} / {len(kept)}')
    print(f'Recuadros grandes filtrados: {discarded} | Recortes: {len(tiles)}')
    print(f'Tiempo total: {elapsed} ms')
    print(f'Visualización: {visual}\nReporte: {report}')

if __name__ == '__main__':
    main()
