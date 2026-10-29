import io
from pathlib import Path
from uuid import uuid4
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import Settings


class InvalidImage(ValueError):
    pass


class ImageTooLarge(InvalidImage):
    pass


class ImagesService:
    def __init__(self, settings: Settings, directory: Path | None = None):
        self.settings = settings
        self.directory = directory if directory is not None else settings.data_dir / "photos"

    def initialize(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def store(self, content: bytes) -> dict:
        if len(content) > self.settings.upload_limit:
            raise ImageTooLarge(f"Cada foto debe pesar como máximo {self.settings.max_upload_mb} MB.")
        if not content:
            raise InvalidImage("La fotografía está vacía.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as image:
                    if image.format not in {"JPEG", "PNG", "WEBP"}:
                        raise InvalidImage("Usa fotografías JPEG, PNG o WebP. No se admiten videos ni HEIC.")
                    if image.width * image.height > self.settings.max_image_pixels:
                        raise ImageTooLarge("La foto excede el límite de píxeles. Reduce su resolución.")
                    if getattr(image, "n_frames", 1) != 1:
                        raise InvalidImage("No se admiten imágenes animadas.")
                    image.verify()
                with Image.open(io.BytesIO(content)) as image:
                    oriented = ImageOps.exif_transpose(image)
                    rgba = oriented.convert("RGBA")
                    normalized = Image.new("RGB", rgba.size, "white")
                    normalized.paste(rgba, mask=rgba.getchannel("A"))
                    normalized.thumbnail((self.settings.normalized_max_side,) * 2, Image.Resampling.LANCZOS)
        except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
            raise ImageTooLarge("La fotografía excede el tamaño seguro de píxeles.") from exc
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            if isinstance(exc, InvalidImage):
                raise
            raise InvalidImage("El archivo no es una fotografía válida o está dañado.") from exc

        photo_id = uuid4().hex
        filename = f"{photo_id}.jpg"
        target = self.directory / filename
        try:
            normalized.save(target, format="JPEG", quality=90)
            return {"id": photo_id, "filename": filename, "width": normalized.width,
                    "height": normalized.height, "size_bytes": target.stat().st_size}
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def delete(self, photo: dict) -> None:
        (self.directory / photo["filename"]).unlink(missing_ok=True)

    def path(self, photo: dict) -> Path:
        return self.directory / photo["filename"]

