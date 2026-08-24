from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
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

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("BOT_TOKEN is required")

        raw_admins = os.getenv("ADMIN_IDS", "").strip()
        admins: set[int] = set()
        if raw_admins:
            for item in raw_admins.split(","):
                item = item.strip()
                if item:
                    try:
                        admins.add(int(item))
                    except ValueError as exc:
                        raise ValueError("ADMIN_IDS must contain numeric Telegram IDs") from exc

        cfg = cls(
            bot_token=token,
            admin_ids=frozenset(admins),
            bot_name=os.getenv("BOT_NAME", "Document Studio").strip(),
            bot_description=os.getenv(
                "BOT_DESCRIPTION", "Private document and image workspace"
            ).strip(),
            database_path=Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3")),
            download_dir=Path(os.getenv("DOWNLOAD_DIR", "downloads")),
            log_dir=Path(os.getenv("LOG_DIR", "logs")),
            job_data_dir=Path(os.getenv("JOB_DATA_DIR", "job-data")),
            max_file_size_mb=_int("MAX_FILE_SIZE_MB", 20, 1),
            max_concurrent_jobs=_int("MAX_CONCURRENT_JOBS", 2, 1),
            max_jobs_per_user=_int("MAX_JOBS_PER_USER", 1, 1),
            max_queue_size=_int("MAX_QUEUE_SIZE", 10, 1),
            download_timeout=_int("DOWNLOAD_TIMEOUT", 120, 1),
            provider_timeout=_int("PROVIDER_TIMEOUT", 60, 1),
            max_retries=_int("MAX_RETRIES", 2, 0),
            rate_limit=_int("RATE_LIMIT", 6, 1),
            rate_window_seconds=_int("RATE_WINDOW_SECONDS", 60, 1),
            auto_cleanup=_bool("AUTO_CLEANUP", True),
            cleanup_after_upload=_bool("CLEANUP_AFTER_UPLOAD", True),
            cleanup_interval_seconds=_int("CLEANUP_INTERVAL_SECONDS", 1800, 30),
            result_ttl_seconds=_int("RESULT_TTL_SECONDS", 86400, 60),
            max_results_per_job=_int("MAX_RESULTS_PER_JOB", 100, 1),
            gallery_page_size=_int("GALLERY_PAGE_SIZE", 6, 1),
            port=_int("PORT", 8080, 1),
            enable_health=_bool("ENABLE_HEALTH", True),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            tesseract_cmd=os.getenv("TESSERACT_CMD", "").strip() or None,
        )
        for path in (cfg.database_path.parent, cfg.download_dir, cfg.log_dir, cfg.job_data_dir):
            path.mkdir(parents=True, exist_ok=True)
        if cfg.gallery_page_size > 10:
            raise ValueError("GALLERY_PAGE_SIZE must be <= 10")
        return cfg
