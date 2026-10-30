"""Carga exclusivamente local de DINO; adapta las dos firmas de Transformers."""
import inspect
from pathlib import Path
from time import perf_counter


class LocalDino:
    source = 'grounding-dino-local'
    last_runtime_ms = None

    def __init__(self, directory: Path, device: str):
        self.directory, self.device = directory, device
        self.model = None

    def initialize(self):
        directory, device = self.directory, self.device
        if not directory.is_dir() or not (directory / 'config.json').is_file():
            raise FileNotFoundError('Falta el checkpoint local de Grounding DINO.')
        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        self.torch, self.device = torch, device
        source = str(directory.resolve())
        self.processor = AutoProcessor.from_pretrained(source, local_files_only=True)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(source, local_files_only=True).to(device).eval()
        parameters = inspect.signature(self.processor.post_process_grounded_object_detection).parameters
        self.threshold_parameter = 'threshold' if 'threshold' in parameters else 'box_threshold'
        if self.threshold_parameter not in parameters:
            raise RuntimeError('Versión incompatible de Transformers: postprocesamiento DINO desconocido.')

    def predict(self, image):
        if self.model is None:
            self.initialize()
        from app.vision.waki_ia.object_detector import DEFAULT_PROMPTS, ObjectCandidate
        started = perf_counter()
        batch = self.processor(images=image.convert('RGB'), text='. '.join(DEFAULT_PROMPTS) + '.',
                               return_tensors='pt').to(self.device)
        with self.torch.inference_mode():
            output = self.model(**batch)
        detected = self.processor.post_process_grounded_object_detection(
            output, batch.input_ids, **{self.threshold_parameter: .35}, text_threshold=.25,
            target_sizes=[(image.height, image.width)],
        )[0]
        candidates = []
        labels = detected.get('text_labels')
        if labels is None:
            labels = detected.get('labels', [])
        for label, score, box in zip(labels, detected['scores'], detected['boxes']):
            coords = [max(0, min(bound, round(float(value))))
                      for value, bound in zip(box, (image.width, image.height, image.width, image.height))]
            if coords[0] < coords[2] and coords[1] < coords[3]:
                candidates.append(ObjectCandidate(str(label), float(score), coords).to_dict())
        self.last_runtime_ms = round((perf_counter() - started) * 1000, 1)
        return sorted(candidates, key=lambda item: item['score_uncalibrated'], reverse=True)[:20]
