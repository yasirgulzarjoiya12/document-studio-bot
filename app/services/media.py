from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable

try:
    import pymupdf as fitz
except ImportError:
    import fitz
from PIL import Image, ImageOps

from .validation import ValidationError
from ..config import Config

Progress = Callable[[int, str], Awaitable[None]]


def _check_cancel(cancel_event: asyncio.Event) -> None:
    if cancel_event.is_set():
        raise asyncio.CancelledError


async def pdf_to_images(src: Path, out_dir: Path, config: Config, progress: Progress, cancel: asyncio.Event) -> list[Path]:
    def work() -> list[Path]:
        doc = fitz.open(src)
        try:
            if doc.page_count > config.max_results_per_job:
                raise ValidationError("PDF has too many pages.")
            outputs = []
            for i, page in enumerate(doc):
                _check_cancel(cancel)
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                out = out_dir / f"page_{i+1:04d}.jpg"
                pix.save(out, jpg_quality=88)
                outputs.append(out)
            return outputs
        finally:
            doc.close()

    outputs = await asyncio.to_thread(work)
    for i, _ in enumerate(outputs, 1):
        await progress(int(i / max(1, len(outputs)) * 100), f"Rendered {i}/{len(outputs)}")
    return outputs


async def images_to_pdf(srcs: list[Path], out: Path, config: Config, progress: Progress, cancel: asyncio.Event) -> list[Path]:
    def work() -> None:
        images = []
        try:
            for p in srcs:
                _check_cancel(cancel)
                with Image.open(p) as im:
                    images.append(ImageOps.exif_transpose(im).convert("RGB").copy())
            first, *rest = images
            first.save(out, "PDF", resolution=150.0, save_all=True, append_images=rest)
        finally:
            for im in images:
                im.close()

    await asyncio.to_thread(work)
    await progress(90, "PDF assembled")
    return [out]


async def merge_pdfs(srcs: list[Path], out: Path, progress: Progress, cancel: asyncio.Event) -> list[Path]:
    def work() -> None:
        result = fitz.open()
        try:
            for p in srcs:
                _check_cancel(cancel)
                with fitz.open(p) as doc:
                    result.insert_pdf(doc)
            result.save(out)
        finally:
            result.close()

    await asyncio.to_thread(work)
    await progress(100, "Merged")
    return [out]


async def split_pdf(src: Path, pages: str, out: Path, progress: Progress, cancel: asyncio.Event) -> list[Path]:
    def work() -> None:
        with fitz.open(src) as source:
            max_pages = source.page_count
            selected = []
            for part in pages.replace(" ", "").split(","):
                if "-" in part:
                    a, b = part.split("-", 1)
                    selected.extend(range(int(a), int(b) + 1))
                else:
                    selected.append(int(part))
            selected = sorted({n - 1 for n in selected if 1 <= n <= max_pages})
            if not selected:
                raise ValidationError("No valid pages.")
            result = fitz.open()
            try:
                for idx in selected:
                    _check_cancel(cancel)
                    result.insert_pdf(source, from_page=idx, to_page=idx)
                result.save(out)
            finally:
                result.close()

    await asyncio.to_thread(work)
    await progress(100, "Split done")
    return [out]


async def extract_text(src: Path, out: Path, progress: Progress, cancel: asyncio.Event) -> list[Path]:
    def work() -> None:
        with fitz.open(src) as doc:
            parts = []
            for i, page in enumerate(doc):
                _check_cancel(cancel)
                parts.append(page.get_text())
            text = "\n".join(parts).strip()
            if not text:
                raise ValidationError("No extractable text in this PDF.")
            out.write_text(text, encoding="utf-8")

    await asyncio.to_thread(work)
    await progress(100, "Text extracted")
    return [out]


async def ocr_image(src: Path, out: Path, config: Config, progress: Progress, cancel: asyncio.Event) -> list[Path]:
    import pytesseract

    if config.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd

    def work() -> None:
        _check_cancel(cancel)
        text = pytesseract.image_to_string(Image.open(src))
        out.write_text(text or "", encoding="utf-8")

    await asyncio.to_thread(work)
    await progress(100, "OCR done")
    return [out]


async def ocr_pdf(src: Path, out: Path, config: Config, progress: Progress, cancel: asyncio.Event) -> list[Path]:
    import pytesseract

    if config.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd

    def work() -> None:
        doc = fitz.open(src)
        parts = []
        try:
            for i, page in enumerate(doc):
                _check_cancel(cancel)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                parts.append(pytesseract.image_to_string(img))
        finally:
            doc.close()
        out.write_text("\n".join(parts), encoding="utf-8")

    await asyncio.to_thread(work)
    await progress(100, "OCR done")
    return [out]


async def compress_pdf(src: Path, out: Path, progress: Progress, cancel: asyncio.Event) -> list[Path]:
    def work() -> None:
        source = fitz.open(src)
        result = fitz.open()
        try:
            for page in source:
                _check_cancel(cancel)
                pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0), alpha=False)
                img_bytes = pix.tobytes("jpeg", jpg_quality=55)
                rect = page.rect
                new_page = result.new_page(width=rect.width, height=rect.height)
                new_page.insert_image(rect, stream=img_bytes)
            result.save(out, deflate=True)
        finally:
            source.close()
            result.close()

    await asyncio.to_thread(work)
    await progress(100, "Compressed")
    return [out]


async def rotate_pdf(src: Path, degrees: int, out: Path, progress: Progress, cancel: asyncio.Event) -> list[Path]:
    def work() -> None:
        with fitz.open(src) as doc:
            for page in doc:
                _check_cancel(cancel)
                page.set_rotation((page.rotation + degrees) % 360)
            doc.save(out)

    await asyncio.to_thread(work)
    await progress(100, "Rotated")
    return [out]
