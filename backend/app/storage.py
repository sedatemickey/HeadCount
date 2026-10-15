import shutil
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


class InvalidImage(ValueError):
    pass


FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


def prepare_image(source: Path, directory: Path, max_pixels: int) -> tuple[str, int, int]:
    """Preserve exact original bytes; coordinates always refer to orientation-corrected display."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as image:
                if image.format not in FORMATS:
                    raise InvalidImage("仅支持 JPEG、PNG、WebP 图片")
                if image.width * image.height > max_pixels:
                    raise InvalidImage("图片像素过大，最多允许 4000 万像素")
                if getattr(image, "n_frames", 1) != 1:
                    raise InvalidImage("不支持动画或多帧图片")
                ext = FORMATS[image.format]
                image.load()
                corrected = ImageOps.exif_transpose(image)
                # Flatten alpha onto white instead of black.
                if corrected.mode in ("RGBA", "LA") or "transparency" in corrected.info:
                    rgba = corrected.convert("RGBA")
                    rgb = Image.new("RGB", rgba.size, "white")
                    rgb.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    rgb = corrected.convert("RGB")
                width, height = rgb.size
                # Do not propagate EXIF/GPS metadata into the browser display image.
                rgb.save(directory / "display.jpg", quality=95)
                rgb.thumbnail((480, 320))
                rgb.save(directory / "thumbnail.jpg", quality=85)
        source.rename(directory / f"original{ext}")
        return ext, width, height
    except InvalidImage:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise InvalidImage("图片损坏、格式不支持或解码像素超限") from exc


def remove_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
