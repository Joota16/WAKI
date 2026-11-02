"""Detección CANDIDATA de objetos visibles con Grounding DINO (sin fine-tuning).

Un resultado es una región candidata para revisión, NO evidencia validada de
obstrucción, basura contaminante ni peligro.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from PIL import Image

DEFAULT_PROMPTS = (
    "plastic bottle", "plastic bag", "garbage bag", "tire",
    "fallen tree trunk", "wood log", "pile of garbage", "concrete block",
)
MODEL_ID = "IDEA-Research/grounding-dino-tiny"


@dataclass
class ObjectCandidate:
    label: str
    score: float  # puntuación del detector; no es probabilidad calibrada
    bbox_xyxy: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "score_uncalibrated": round(float(self.score), 4),
            "bbox_xyxy": [int(v) for v in self.bbox_xyxy],
            "interpretation": "Candidato visual no verificado; requiere confirmación humana.",
        }


class GroundingDinoDetector:
    def __init__(self, device: str = "cpu", source: str = MODEL_ID):
        import torch
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        self.torch = torch
        self.device = device
        self.source = source
        self.processor = AutoProcessor.from_pretrained(source)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(source).to(device).eval()

    def predict(self, image: Image.Image, prompts=DEFAULT_PROMPTS,
                box_threshold: float = 0.35, text_threshold: float = 0.25,
                max_candidates: int = 20) -> list[dict[str, Any]]:
        if not prompts:
            return []
        text = ". ".join(prompts) + "."
        batch = self.processor(images=image.convert("RGB"), text=text, return_tensors="pt").to(self.device)
        with self.torch.inference_mode():
            outputs = self.model(**batch)
        detected = self.processor.post_process_grounded_object_detection(
            outputs, batch.input_ids,
            threshold=box_threshold, text_threshold=text_threshold,
            target_sizes=[(image.height, image.width)],
        )[0]
        labels = detected.get("text_labels", detected.get("labels", []))
        candidates = []
        for label, score, box in zip(labels, detected["scores"], detected["boxes"]):
            bounds = box.tolist() if hasattr(box, "tolist") else list(box)
            x1, y1, x2, y2 = bounds
            bounded = [
                max(0, min(image.width, round(float(x1)))),
                max(0, min(image.height, round(float(y1)))),
                max(0, min(image.width, round(float(x2)))),
                max(0, min(image.height, round(float(y2)))),
            ]
            if bounded[2] <= bounded[0] or bounded[3] <= bounded[1]:
                continue
            candidates.append(ObjectCandidate(str(label), float(score), bounded).to_dict())
        candidates.sort(key=lambda p: p["score_uncalibrated"], reverse=True)
        return candidates[:max_candidates]


@lru_cache(maxsize=2)
def get_detector(device: str = "cpu", source: str = MODEL_ID):
    return GroundingDinoDetector(device=device, source=source)
