from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str, default: str = "file") -> str:
    base = Path(name).name
    base = _SAFE.sub("_", base).strip("._")
    return base[:120] or default


def new_job_id() -> str:
    return uuid4().hex


def callback_owner(data: str) -> int | None:
    parts = data.split(":")
    if len(parts) < 2:
        return None
    try:
        return int(parts[-1])
    except ValueError:
        return None
