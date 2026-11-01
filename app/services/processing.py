"""Captura -> trabajo independiente -> motor -> informe y artefactos locales."""
import json
import logging
import math
from pathlib import Path
import shutil
import threading
from uuid import UUID, uuid4

from app.config import Settings
from app.repositories.analyses import AnalysesRepository, utcnow
from app.schemas.analyses import AnalysisList, AnalysisOut, STATUS_LABELS
from app.services.images import ImagesService
from app.vision.service import VisionProvider

logger = logging.getLogger(__name__)
ARTIFACTS = {
    'image_original': 'original.jpg', 'mask': 'mascara_agua.png',
    'water_overlay': 'segmentacion.jpg', 'objects_overlay': 'objetos.jpg',
    'combined_overlay': 'analisis_combinado.jpg',
}


class AnalysisNotFound(LookupError):
    pass


class AnalysisBusy(ValueError):
    pass


class ProcessingService:
    def __init__(self, repository: AnalysesRepository, provider: VisionProvider, settings: Settings):
        self.repository, self.provider, self.settings = repository, provider, settings
        self.directory = settings.data_dir / 'analyses'
        self.lock = threading.Lock()

    def initialize(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.repository.interrupt_pending()
        referenced = self.repository.ids()
        for folder in self.directory.iterdir():
            if folder.is_dir() and folder.name not in referenced:
                shutil.rmtree(folder)

    def enqueue(self, frame: dict, river_id: str, image: bytes, *, source: str = 'iot'):
        analysis_id = UUID(frame['id']).hex
        folder = self.directory / analysis_id
        folder.mkdir()
        try:
            (folder / 'input.jpg').write_bytes(image)
            issue = self.provider.configuration_issue(river_id)
            expired = self.repository.add({
                'id': analysis_id, 'camera_id': frame['camera_id'], 'river_id': river_id, 'source': source,
                'received_at': frame['received_at'], 'captured_at': frame['captured_at'], 'created_at': utcnow(),
                'status': 'not_configured' if issue else 'queued', 'message': issue or '',
            }, self.settings.ai_max_pending, self.settings.ai_retention_images)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        for old_id in expired:
            shutil.rmtree(self.directory / old_id, ignore_errors=True)

    def create_test(self, river_id: str, content: bytes) -> AnalysisOut:
        normalized = ImagesService(self.settings).normalized_bytes(content)
        analysis_id = uuid4().hex
        self.enqueue({'id': analysis_id, 'camera_id': f'test-{river_id}', 'received_at': utcnow(),
                      'captured_at': None}, river_id, normalized, source='test')
        return self.get(analysis_id)

    def process(self, analysis_id: str):
        """BackgroundTasks llama este método síncrono fuera del bucle HTTP."""
        analysis_id = UUID(analysis_id).hex
        pending = self.repository.get(analysis_id)
        if pending is None or pending['status'] != 'queued':
            return
        with self.lock:
            if not self.repository.claim(analysis_id):
                return
            row = self.repository.get(analysis_id)
            output = self.directory / analysis_id / 'result'
            try:
                shutil.rmtree(output, ignore_errors=True)
                output.mkdir()
                result, files = self.provider.analyze(self.directory / analysis_id / 'input.jpg', {
                    'source': row['source'], 'point_id': str(UUID(analysis_id)),
                    'camera_id': row['camera_id'] if row['source'] == 'iot' else None,
                    'captured_at': row['captured_at'],
                }, output)
                status, message = self.outcome(result)
                if any(key not in ARTIFACTS or name != ARTIFACTS[key] or not (output / name).is_file()
                       for key, name in files.items()):
                    raise ValueError('El proveedor devolvió artefactos inválidos.')
                if status in ('analyzed', 'partial') and not files:
                    raise ValueError('El proveedor no guardó imágenes de resultado.')
                self.repository.finish(analysis_id, status, message, result, files)
            except Exception:
                logger.exception('Falló el análisis de la captura %s', analysis_id)
                self.repository.finish(analysis_id, 'error', 'No se pudo completar la inferencia. Se conserva la fotografía; requiere reintento.')
            finally:
                for old_id in self.repository.prune(row['camera_id'], self.settings.ai_retention_images):
                    shutil.rmtree(self.directory / old_id, ignore_errors=True)

    @staticmethod
    def outcome(result: dict) -> tuple[str, str]:
        if result.get('analysis_mode') != 'live_models':
            raise ValueError('Solo se aceptan inferencias nuevas; no reproducciones de resultados.')
        modules = result['modules']
        water = modules['water_segmentation']
        water_ok = water.get('status') in ('predicted_nonempty', 'predicted_empty_needs_review')
        if water_ok:
            ratio = water['fraction_of_image_predicted_as_water']
            if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or not 0 <= ratio <= 1:
                raise ValueError('Proporción de agua inválida.')
        objects = modules['object_candidates']
        statuses = objects.get('model_status', {}).values()
        objects_ok = any(item.get('status') == 'processed' for item in statuses)
        objects_failed = any(item.get('status') == 'error' for item in statuses)
        if not water_ok and not objects_ok:
            return 'error', 'Fallaron los módulos de inferencia. No equivale a ausencia de agua u objetos.'
        if not water_ok or not objects_ok or objects_failed:
            return 'partial', 'Resultado parcial: consulta los módulos disponibles en el informe.'
        return 'analyzed', 'Resultados generados. Pendientes de revisión humana.'

    def row(self, analysis_id: UUID | str):
        row = self.repository.get(UUID(str(analysis_id)).hex)
        if row is None:
            raise AnalysisNotFound('El informe de IA no existe o venció su retención.')
        return row

    def public(self, row: dict, include_result=False) -> AnalysisOut:
        analysis_id = str(UUID(row['id']))
        base = f'/api/analyses/{analysis_id}'
        result = json.loads(row['result_json']) if row['result_json'] else None
        files = json.loads(row['artifacts_json'])
        links = {key: f'{base}/artifacts/{key}' for key in files if key in ARTIFACTS}
        modules = result.get('modules', {}) if result else {}
        water = modules.get('water_segmentation', {})
        objects = modules.get('object_candidates', {})
        available = any(item.get('status') == 'processed' for item in objects.get('model_status', {}).values())
        if water.get('status') not in ('predicted_nonempty', 'predicted_empty_needs_review'):
            links.pop('water_overlay', None)
            links.pop('mask', None)
        if not available:
            links.pop('objects_overlay', None)
        if row['status'] not in ('analyzed', 'partial'):
            links.pop('combined_overlay', None)
        test = row['source'] == 'test'
        return AnalysisOut(**{key: value for key, value in row.items() if key not in ('id', 'status', 'camera_id')},
                           id=analysis_id, frame_id=None if test else analysis_id,
                           camera_id=None if test else row['camera_id'], source_label='Prueba manual' if test else 'Cámara',
                           status=row['status'], status_label=STATUS_LABELS[row['status']],
                           water_fraction=water.get('fraction_of_image_predicted_as_water'),
                           candidate_count=len(objects.get('candidates', [])) if available else None,
                           objects_available=available, original_url=f'{base}/artifacts/original',
                           overlay_url=links.get('combined_overlay') if row['status'] in ('analyzed', 'partial') else None,
                           artifacts=links, report_url=f'/informes-ia/{analysis_id}', result=result if include_result else None)

    def get(self, analysis_id: UUID | str):
        return self.public(self.row(analysis_id), include_result=True)

    def list(self, camera_id: str, limit: int, offset: int):
        rows, total = self.repository.list(camera_id, limit, offset)
        return AnalysisList(items=[self.public(row) for row in rows], total=total, limit=limit, offset=offset)

    def list_tests(self, river_id: str, limit: int, offset: int):
        return self.list(f'test-{river_id}', limit, offset)

    def artifact(self, analysis_id: UUID, kind: str) -> tuple[bytes, str]:
        row = self.row(analysis_id)
        folder = self.directory / UUID(row['id']).hex
        files = json.loads(row['artifacts_json'])
        if kind == 'original':
            path = folder / 'input.jpg'
        elif kind in ARTIFACTS and files.get(kind) == ARTIFACTS[kind]:
            path = folder / 'result' / ARTIFACTS[kind]
        else:
            raise AnalysisNotFound('Este artefacto no está disponible.')
        try:
            return path.read_bytes(), 'image/png' if kind == 'mask' else 'image/jpeg'
        except FileNotFoundError as exc:
            raise AnalysisNotFound('El archivo no está disponible.') from exc

    def retry(self, analysis_id: UUID):
        row = self.row(analysis_id)
        issue = self.provider.configuration_issue(row['river_id'])
        if not self.repository.retry(UUID(row['id']).hex, self.settings.ai_max_pending,
                                     'not_configured' if issue else 'queued', issue or ''):
            raise AnalysisBusy('El análisis está en curso, ya terminó o la cola está llena.')
        return self.get(analysis_id)

