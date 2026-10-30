"""Una interfaz común: SegFormer B0, B1 y checkpoint ajustado de WAKI.

NO calcula riesgo, altura, caudal ni alertas de inundación.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Union

import numpy as np
from PIL import Image

MODEL_IDS = {
    "segformer_b0": "nvidia/segformer-b0-finetuned-ade-512-512",
    "segformer_b1": "nvidia/segformer-b1-finetuned-ade-512-512",
}
WATER_NAMES = {"water", "river", "sea", "lake", "waterfall"}


def aspect_dims(width: int, height: int, longest: int = 768) -> tuple[int, int]:
    scale = longest / max(width, height)
    out_w = max(32, int(round(width * scale / 32) * 32))
    out_h = max(32, int(round(height * scale / 32) * 32))
    return out_w, out_h


def mask_overlay(original: Image.Image, water: np.ndarray) -> Image.Image:
    rgb = np.asarray(original.convert("RGB"), dtype=np.float32).copy()
    if water.shape != rgb.shape[:2]:
        raise ValueError("La máscara debe tener las mismas dimensiones que la imagen")
    rgb[water] = rgb[water] * 0.55 + np.array([0, 191, 209], dtype=np.float32) * 0.45
    return Image.fromarray(rgb.clip(0, 255).astype(np.uint8), mode="RGB")


@dataclass
class Prediction:
    mask: np.ndarray  # bool H x W: TRUE equivale a agua predicha
    overlay: Image.Image
    report: dict


class RiverWaterSegmenter:
    """Cargar una vez por proceso. Admite predicción independiente del backend."""

    def __init__(self, name: str = "segformer_b0", *, checkpoint: str | None = None,
                 device: str = "cpu", longest_side: int = 768):
        try:
            import torch
            from transformers import AutoImageProcessor, SegformerForSemanticSegmentation
        except ImportError as exc:
            raise RuntimeError("Instala las dependencias: pip install -r requirements.txt") from exc

        if checkpoint:
            source = str(checkpoint)
            if Path(source).exists():
                source = str(Path(source).resolve())
        else:
            if name not in MODEL_IDS:
                raise ValueError(f"Modelo desconocido: {name}. Disponibles: {', '.join(MODEL_IDS)}")
            local = Path(__file__).resolve().parents[1] / "models" / name
            source = str(local.resolve()) if (local / "config.json").exists() else MODEL_IDS[name]

        self.torch = torch
        self.source = source
        self.name = name if not checkpoint else "segformer_custom"
        self.device = device
        self.longest_side = longest_side
        self.processor = AutoImageProcessor.from_pretrained(source)
        self.model = SegformerForSemanticSegmentation.from_pretrained(source).to(device).eval()
        labels = {int(k): str(v).strip().lower() for k, v in self.model.config.id2label.items()}
        self.water_ids = tuple(sorted(k for k, v in labels.items() if v in WATER_NAMES))
        if not self.water_ids:
            raise ValueError(f"El modelo {source} no declara ninguna clase de agua en id2label: {labels}")

    def predict(self, image: Union[Image.Image, str, Path, bytes]) -> Prediction:
        import io
        import torch.nn.functional as F

        if isinstance(image, (str, Path)):
            with Image.open(image) as loaded:
                img = loaded.convert("RGB")
        elif isinstance(image, bytes):
            with Image.open(io.BytesIO(image)) as loaded:
                img = loaded.convert("RGB")
        elif isinstance(image, Image.Image):
            img = image.convert("RGB")
        else:
            raise TypeError("Se requiere PIL.Image, bytes o ruta de archivo")

        width, height = img.size
        model_w, model_h = aspect_dims(width, height, self.longest_side)
        batch = self.processor(images=img, size={"height": model_h, "width": model_w},
                               return_tensors="pt").to(self.device)
        start = perf_counter()
        with self.torch.inference_mode():
            logits = self.model(**batch).logits.cpu()

        # Reescalar en franjas para evitar el gran uso de RAM de 150 clases x fotografía completa.
        water = np.zeros((height, width), dtype=bool)
        xx = (self.torch.arange(width, dtype=self.torch.float32) + .5) * (2.0 / width) - 1.0
        for y0 in range(0, height, 32):
            y1 = min(height, y0 + 32)
            yy = (self.torch.arange(y0, y1, dtype=self.torch.float32) + .5) * (2.0 / height) - 1.0
            gy, gx = self.torch.meshgrid(yy, xx, indexing="ij")
            grid = self.torch.stack((gx, gy), dim=-1).unsqueeze(0)
            with self.torch.inference_mode():
                raw = F.grid_sample(logits, grid, mode="bilinear",
                                    padding_mode="border", align_corners=False)[0].argmax(dim=0)
            water[y0:y1] = np.isin(raw.numpy(), self.water_ids)
        elapsed = round((perf_counter() - start) * 1000, 1)
        report = {
            "schema_version": "1.0", "status": "processed", "model_name": self.name,
            "model_checkpoint": self.source,
            "image_width": width, "image_height": height,
            "water_pixels_detected": int(water.sum()),
            "water_fraction": round(float(water.mean()), 6),
            "inference_ms": elapsed,
            "risk_level": None,
            "interpretation": "Máscara visual del agua predicha; no equivale a nivel, caudal o riesgo.",
            "warning": "Si el modelo devuelve cero agua, NO significa que el río esté seco. Requiere revisión.",
        }
        return Prediction(mask=water, overlay=mask_overlay(img, water), report=report)


@lru_cache(maxsize=3)
def _cached_model(name: str, checkpoint: str | None, device: str, longest_side: int):
    return RiverWaterSegmenter(name=name, checkpoint=checkpoint,
                               device=device, longest_side=longest_side)


def predict_image(image: Union[Image.Image, str, Path, bytes],
                  model_name: str = "segformer_b0", checkpoint: str | None = None,
                  device: str = "cpu", longest_side: int = 768) -> Prediction:
    """Interfaz más sencilla para el compañero integrador; cachea el modelo entre peticiones."""
    return _cached_model(model_name, checkpoint, device, longest_side).predict(image)
