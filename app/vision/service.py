"""Contrato de inferencia, sin importar modelos al iniciar la web."""
from pathlib import Path
from typing import Protocol

from app.config import Settings


class VisionProvider(Protocol):
    def configuration_issue(self, river_id: str) -> str | None: ...
    def analyze(self, image: Path, context: dict, output: Path) -> tuple[dict, dict[str, str]]: ...


class NoVision:
    def configuration_issue(self, river_id: str) -> str:
        return 'El análisis de IA está desactivado. La fotografía se conserva sin resultados inventados.'


def build_provider(settings: Settings) -> VisionProvider:
    if settings.model_provider == 'none':
        return NoVision()
    from app.vision.providers.waki import WakiProvider
    return WakiProvider(settings)

