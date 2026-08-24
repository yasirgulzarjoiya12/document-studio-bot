from __future__ import annotations

from pathlib import Path

from .job_manager import RuntimeJob
from .media import (
    compress_pdf,
    extract_text,
    images_to_pdf,
    merge_pdfs,
    ocr_image,
    ocr_pdf,
    pdf_to_images,
    rotate_pdf,
    split_pdf,
)
from .validation import ValidationError
from ..config import Config


async def run(job: RuntimeJob, progress, config: Config) -> list[Path]:
    out = config.job_data_dir / job.job_id / "output"
    out.mkdir(parents=True, exist_ok=True)
    inputs = job.inputs
    op = job.operation

    await progress(5, "Preparing input")
    if op == "pdfimg":
        return await pdf_to_images(inputs[0], out, config, progress, job.cancel)
    if op == "imgpdf":
        return await images_to_pdf(inputs, out / "images.pdf", config, progress, job.cancel)
    if op == "merge":
        return await merge_pdfs(inputs, out / "merged.pdf", progress, job.cancel)
    if op == "split":
        return await split_pdf(inputs[0], job.params["pages"], out / "split.pdf", progress, job.cancel)
    if op == "text":
        return await extract_text(inputs[0], out / "extracted.txt", progress, job.cancel)
    if op == "ocr":
        if inputs[0].suffix.lower() == ".pdf":
            return await ocr_pdf(inputs[0], out / "ocr.txt", config, progress, job.cancel)
        return await ocr_image(inputs[0], out / "ocr.txt", config, progress, job.cancel)
    if op == "compress":
        return await compress_pdf(inputs[0], out / "compressed.pdf", progress, job.cancel)
    if op == "rotate":
        return await rotate_pdf(
            inputs[0], int(job.params["degrees"]), out / "rotated.pdf", progress, job.cancel
        )
    raise ValidationError("Unknown operation.")
