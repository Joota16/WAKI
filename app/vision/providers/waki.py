"""Adaptador de WAKI: pesos locales, carga diferida y motor original intacto."""
import importlib.util
import json
import os
from pathlib import Path

from app.config import Settings


class WakiProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.water = None
        self.dino = None
        self.yoloe = None

    def configuration_issue(self, river_id: str) -> str | None:
        if river_id not in {item.strip() for item in self.settings.ai_rivers.split(',')}:
            return 'El modelo no está habilitado para este río.'
        checkpoint = self.settings.ai_water_checkpoint
        if not all((checkpoint / file).is_file() for file in ('config.json', 'preprocessor_config.json', 'model.safetensors')):
            return 'Falta el checkpoint local de segmentación. No se descargan modelos automáticamente.'
        missing = [name for name in ('torch', 'transformers', 'numpy', 'cv2', 'safetensors')
                   if importlib.util.find_spec(name) is None]
        if missing:
            return 'Faltan dependencias opcionales de IA. Consulta la guía de integración.'
        return None

    def analyze(self, image: Path, context: dict, output: Path) -> tuple[dict, dict[str, str]]:
        # Se fijan antes de importar Transformers. El adaptador nunca usa IDs remotos.
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['YOLO_AUTOINSTALL'] = 'false'
        os.environ['YOLO_OFFLINE'] = 'true'
        from app.vision.waki_ia import analizar_waki, guardar_resultado
        from app.vision.waki_ia.inference import RiverWaterSegmenter

        if self.water is None:
            self.water = RiverWaterSegmenter(checkpoint=str(self.settings.ai_water_checkpoint.resolve()),
                                             device=self.settings.ai_device)
        if self.settings.ai_dino_checkpoint is not None and self.dino is None:
            from app.vision.providers.local_dino import LocalDino
            self.dino = LocalDino(self.settings.ai_dino_checkpoint, self.settings.ai_device)
        if self.settings.ai_yoloe_checkpoint is not None and self.yoloe is None:
            from app.vision.providers.local_yoloe import LocalYoloe
            self.yoloe = LocalYoloe(self.settings.ai_yoloe_checkpoint, self.settings.ai_yoloe_prompts,
                                   self.settings.ai_device)
        report, artifacts = analizar_waki(
            image, contexto=context, perfil_agua='chillon', dispositivo=self.settings.ai_device,
            predictor_agua=self.water.predict, detectar_objetos=self.dino is not None or self.yoloe is not None,
            usar_yoloe=self.yoloe is not None, detector_yoloe=self.yoloe,
            usar_dino=self.dino is not None, detector_dino=self.dino,
        )
        # Los resultados no exponen rutas del sistema de archivos del servidor.
        report['modules']['water_segmentation'].pop('checkpoint', None)
        for name, module in report['modules']['object_candidates'].get('model_status', {}).items():
            if module.get('status') == 'processed':
                module['model'] = 'grounding-dino-local' if name == 'grounding_dino' else 'yoloe-local'
        if self.dino is None and self.yoloe is None:
            report['summary']['observations'].append('Detección de objetos sin configurar: faltan los checkpoints locales de los detectores.')
        saved = guardar_resultado(report, artifacts, output)
        persisted = json.loads(saved.read_text(encoding='utf-8'))
        return persisted, persisted['artifacts_relative_paths']
