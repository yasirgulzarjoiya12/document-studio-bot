from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Job:
    job_id: str
    user_id: int
    chat_id: int
    operation: str
    status: JobStatus
    progress: int
    input_meta: dict[str, Any]
    output_count: int
    error: str | None
    retry_count: int


@dataclass(slots=True)
class Result:
    result_id: int
    job_id: str
    path: Path
    media_type: str
    original_name: str
    size_bytes: int
