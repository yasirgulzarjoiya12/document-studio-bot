from __future__ import annotations

import shutil
from pathlib import Path


def ensure_inside(base: Path, path: Path) -> Path:
    base = base.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError("Path escapes job directory") from exc
    return resolved


def copy_to_job(source: Path, job_dir: Path, name: str) -> Path:
    destination = ensure_inside(job_dir, job_dir / name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination
