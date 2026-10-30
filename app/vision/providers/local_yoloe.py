"""YOLOE multiescala con pesos y embeddings locales, sin codificador remoto."""
import os
from pathlib import Path


class LocalYoloe:
    source = 'yoloe-local'
    last_runtime_ms = None

    def __init__(self, checkpoint: Path, prompts: Path | None, device: str):
        self.checkpoint, self.prompts, self.device = checkpoint, prompts, device
        self.detector = None

    def initialize(self):
        if not self.checkpoint.is_file() or self.checkpoint.suffix != '.pt':
            raise FileNotFoundError('Faltan los pesos locales de YOLOE.')
        if self.prompts is None or not self.prompts.is_file():
            raise FileNotFoundError('Faltan los prompts locales de YOLOE.')
        os.environ['YOLO_AUTOINSTALL'] = 'false'
        os.environ['YOLO_OFFLINE'] = 'true'
        os.environ.setdefault('YOLO_CONFIG_DIR', '/tmp/waki-ultralytics')
        (Path(os.environ['YOLO_CONFIG_DIR']) / 'Ultralytics').mkdir(parents=True, exist_ok=True)
        from ultralytics import YOLOE
        from app.vision.waki_ia.hybrid_report import YoloeMultiscaleAdapter
        from app.vision.waki_ia.yoloe_multiscale import DEFAULT_CLASSES

        model = YOLOE(str(self.checkpoint.resolve()))
        if model.task != 'segment':
            raise ValueError('Se requiere un checkpoint YOLOE de segmentación.')
        # La API valida arquitectura, clases, dimensión y valores finitos del NPZ.
        # Al suministrar embeddings no se ejecuta get_text_pe ni se descarga CLIP.
        model.load_prompt_embeddings(str(self.prompts.resolve()))
        names = list(model.names.values()) if isinstance(model.names, dict) else list(model.names)
        if names != DEFAULT_CLASSES:
            raise ValueError('Las clases del NPZ no coinciden con las clases del motor WAKI.')
        # Ultralytics admite otro objeto Model como argumento: reutilizamos el
        # modelo preparado y el algoritmo original de imagen completa + recortes.
        detector = YoloeMultiscaleAdapter(device=self.device, weights=model)
        detector.source = self.source
        self.detector = detector

    def predict(self, image):
        if self.detector is None:
            self.initialize()
        result = self.detector.predict(image)
        self.last_runtime_ms = self.detector.last_runtime_ms
        return result
