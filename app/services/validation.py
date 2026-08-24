from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ..config import Config


class ValidationError(Exception):
    pass


@dataclass(slots=True)
class ValidatedFile:
    path: Path
    media_type: str
    size_bytes: int


def _read_header(path: Path) -> bytes:
    try:
        with path.open("rb") as fh:
            return fh.read(16)
    except OSError as exc:
        raise ValidationError("The output file could not be read.") from exc


def validate_file(path: Path, config: Config, expected: str | None = None) -> ValidatedFile:
    if not path.exists() or not path.is_file():
        raise ValidationError("Output file does not exist.")
    size = path.stat().st_size
    if size <= 0:
        raise ValidationError("Output file is empty.")
    if size > config.max_file_size_bytes:
        raise ValidationError("Output file exceeds the configured Telegram size limit.")
    _read_header(path)

    suffix = path.suffix.lower()
    media = "document"
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        media = "image"
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
                if image.width < 1 or image.height < 1:
                    raise ValidationError("Image has invalid dimensions.")
        except (UnidentifiedImageError, OSError) as exc:
            raise ValidationError("Image validation failed.") from exc
    elif suffix == ".pdf":
        media = "pdf"
        if not _read_header(path).startswith(b"%PDF-"):
            raise ValidationError("PDF signature is invalid.")
        try:
            import fitz
            doc = fitz.open(path)
            pages = doc.page_count
            doc.close()
            if pages < 1:
                raise ValidationError("PDF contains no pages.")
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError("PDF validation failed.") from exc
    elif suffix == ".zip":
        media = "archive"
        if not zipfile.is_zipfile(path):
            raise ValidationError("ZIP archive validation failed.")
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad:
                raise ValidationError("ZIP archive is corrupted.")
    elif suffix == ".txt":
        media = "text"
        with path.open("rb") as fh:
            fh.read(4096)

    if expected and media != expected:
        raise ValidationError(f"Output type mismatch: expected {expected}, got {media}.")
    return ValidatedFile(path, media, size)


def validate_input(path: Path, config: Config, allowed: set[str]) -> ValidatedFile:
    if not path.exists() or not path.is_file():
        raise ValidationError("Input file does not exist.")
    if path.stat().st_size <= 0:
        raise ValidationError("Input file is empty.")
    if path.stat().st_size > config.max_file_size_bytes:
        raise ValidationError("Input file is larger than the configured limit.")
    suffix = path.suffix.lower()
    if suffix not in allowed:
        raise ValidationError("Unsupported file type for this operation.")
    return validate_file(path, config)
