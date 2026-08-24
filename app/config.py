from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: list[int]
    bot_name: str
    bot_description: str
    database_path: Path
    download_dir: Path
    log_dir: Path
    job_data_dir: Path
    max_file_size_mb: int
    max_concurrent_jobs: int
    max_jobs_per_user: int
    max_queue_size: int
    download_timeout: int
    provider_timeout: int
    max_retries: int
    rate_limit: int
    rate_window_seconds: int
    auto_cleanup: bool
    cleanup_after_upload: bool
    cleanup_interval_seconds: int
    result_ttl_seconds: int
    max_results_per_job: int
    gallery_page_size: int
    port: int
    enable_health: bool
    log_level: str
    tesseract_cmd: str | None


def _bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _int_list(val: str | None) -> list[int]:
    if not val:
        return []
    out = []
    for part in val.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is required")

    base = Path(".").resolve()
    return Settings(
        bot_token=token,
        admin_ids=_int_list(os.getenv("ADMIN_IDS")),
        bot_name=os.getenv("BOT_NAME", "Document Studio").strip() or "Document Studio",
        bot_description=os.getenv("BOT_DESCRIPTION", "Private document and image workspace").strip(),
        database_path=base / os.getenv("DATABASE_PATH", "data/bot.sqlite3"),
        download_dir=base / os.getenv("DOWNLOAD_DIR", "downloads"),
        log_dir=base / os.getenv("LOG_DIR", "logs"),
        job_data_dir=base / os.getenv("JOB_DATA_DIR", "job-data"),
        max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "20")),
        max_concurrent_jobs=int(os.getenv("MAX_CONCURRENT_JOBS", "2")),
        max_jobs_per_user=int(os.getenv("MAX_JOBS_PER_USER", "1")),
        max_queue_size=int(os.getenv("MAX_QUEUE_SIZE", "10")),
        download_timeout=int(os.getenv("DOWNLOAD_TIMEOUT", "120")),
        provider_timeout=int(os.getenv("PROVIDER_TIMEOUT", "60")),
        max_retries=int(os.getenv("MAX_RETRIES", "2")),
        rate_limit=int(os.getenv("RATE_LIMIT", "6")),
        rate_window_seconds=int(os.getenv("RATE_WINDOW_SECONDS", "60")),
        auto_cleanup=_bool(os.getenv("AUTO_CLEANUP"), True),
        cleanup_after_upload=_bool(os.getenv("CLEANUP_AFTER_UPLOAD"), True),
        cleanup_interval_seconds=int(os.getenv("CLEANUP_INTERVAL_SECONDS", "1800")),
        result_ttl_seconds=int(os.getenv("RESULT_TTL_SECONDS", "86400")),
        max_results_per_job=int(os.getenv("MAX_RESULTS_PER_JOB", "100")),
        gallery_page_size=int(os.getenv("GALLERY_PAGE_SIZE", "6")),
        port=int(os.getenv("PORT", "8080")),
        enable_health=_bool(os.getenv("ENABLE_HEALTH"), True),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        tesseract_cmd=os.getenv("TESSERACT_CMD") or None,
    )
