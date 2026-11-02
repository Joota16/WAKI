"""Interfaz pública estable WAKI 4.1. Nunca calcula riesgo hidrológico."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from PIL import Image
from .hybrid_report import analyze_hybrid_observation, save_hybrid_outputs

WATER_PROFILES = ('clasico', 'chillon')
DEFAULT_CHILLON_CHECKPOINT = Path('models/segformer_chillon_finetuned')


def _checkpoint_for(profile: str, checkpoint: str | Path | None):
    if profile not in WATER_PROFILES:
        raise ValueError('perfil_agua debe ser clasico o chillon')
    if profile == 'clasico':
        if checkpoint is not None:
            raise ValueError('El perfil clasico no admite checkpoint. Usa perfil_agua=chillon.')
        return None
    location = Path(checkpoint or DEFAULT_CHILLON_CHECKPOINT)
    if not (location.is_dir() and (location / 'config.json').is_file()):
        raise FileNotFoundError(f'Falta config.json del checkpoint ajustado en: {location}')
    if not any((location / name).is_file() for name in ('model.safetensors', 'pytorch_model.bin')):
        raise FileNotFoundError(f'Faltan los pesos del checkpoint ajustado en: {location}')
    return str(location.resolve())


def analizar_waki(
    imagen: Image.Image | bytes | str | Path, *,
    contexto: dict | None = None,
    perfil_agua: str = 'clasico',
    checkpoint: str | Path | None = None,
    dispositivo: str = 'cuda',
    detectar_objetos: bool = True,
    usar_yoloe: bool = True,
    usar_dino: bool = True,
    detector_yoloe: Any = None,
    detector_dino: Any = None,
    predictor_agua: Any = None,
    mascara_agua_precalculada: Any = None,
    predicciones_yoloe: list[dict] | None = None,
    predicciones_dino: list[dict] | None = None,
):
    """Devuelve (reporte JSON serializable, artefactos PIL/numpy).

    Por defecto usa el SegFormer B0 clásico que segmentó 43.25% de la foto demo.
    El perfil 'chillon' requiere pesos locales, no suministrados en este ZIP.
    Los argumentos precomputados se destinan solo a pruebas/reproducción.
    """
    if mascara_agua_precalculada is None and predictor_agua is None:
        selected_checkpoint = _checkpoint_for(perfil_agua, checkpoint)
    else:
        if perfil_agua not in WATER_PROFILES:
            raise ValueError('perfil_agua debe ser clasico o chillon')
        selected_checkpoint = None
    report, artifacts = analyze_hybrid_observation(
        imagen, context=contexto, checkpoint=selected_checkpoint, device=dispositivo,
        use_yoloe=detectar_objetos and usar_yoloe,
        use_dino=detectar_objetos and usar_dino,
        yoloe_detector=detector_yoloe, dino_detector=detector_dino,
        water_predictor=predictor_agua,
        precomputed_water_mask=mascara_agua_precalculada,
        replay_yoloe=predicciones_yoloe,
        replay_dino=predicciones_dino,
    )
    report['schema_version'] = '4.1'
    report['modules']['water_segmentation']['requested_profile'] = perfil_agua
    report['summary']['water_profile'] = perfil_agua
    report['summary']['object_detection_experimental'] = True
    report['summary']['risk_level'] = None
    report['summary']['inspection_priority'] = None
    return report, artifacts


def guardar_resultado(reporte: dict, artefactos: dict, salida: str | Path) -> Path:
    return save_hybrid_outputs(reporte, artefactos, salida)
