"""Métricas binaria agua/no agua; 255 = ignorar."""
import numpy as np


def confusion_counts(predicted, reference):
    pred = np.asarray(predicted)
    ref = np.asarray(reference)
    if pred.shape != ref.shape:
        raise ValueError(f"Dimensiones diferentes: pred={pred.shape}, ref={ref.shape}")
    vals = set(np.unique(ref).tolist())
    if not vals.issubset({0, 1, 255}):
        raise ValueError(f"Máscara de referencia debe contener solo 0, 1 o 255; encontrado: {vals}")
    valid = ref != 255
    predicted_water = np.asarray(pred, dtype=bool)
    reference_water = ref == 1
    tp = int(np.count_nonzero(predicted_water & reference_water & valid))
    fp = int(np.count_nonzero(predicted_water & ~reference_water & valid))
    fn = int(np.count_nonzero(~predicted_water & reference_water & valid))
    return tp, fp, fn


def metrics_from_counts(tp, fp, fn):
    # None cuando una métrica no está definida; evita dar valor 100% sin agua.
    def safe(a, b):
        return float(a / b) if b else None
    precision = safe(tp, tp + fp)
    recall = safe(tp, tp + fn)
    iou = safe(tp, tp + fp + fn)
    f1 = safe(2 * tp, 2 * tp + fp + fn)
    return {"iou_agua": iou, "precision_agua": precision,
            "recall_agua": recall, "f1_agua": f1}
