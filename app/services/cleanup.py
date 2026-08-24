from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path

from ..config import Config
from ..database import Database


log = logging.getLogger(__name__)


class CleanupService:
    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.task: asyncio.Task | None = None
        self.stop_event = asyncio.Event()

    def start(self) -> None:
        if self.config.auto_cleanup and self.task is None:
            self.task = asyncio.create_task(self._loop(), name="cleanup")
            self.task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            log.error("Cleanup task crashed: %s", exc, exc_info=exc)

    async def stop(self) -> None:
        self.stop_event.set()
        if self.task:
            await self.task
            self.task = None

    async def _loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                await self.sweep()
            except Exception:
                log.exception("Cleanup sweep failed")
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=self.config.cleanup_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def sweep(self) -> None:
        retention = self.config.result_ttl_seconds if self.config.cleanup_after_upload else self.config.result_ttl_seconds * 2
        cutoff = time.time() - retention
        for child in self.config.job_data_dir.iterdir():
            if child.is_dir():
                try:
                    if child.stat().st_mtime < cutoff:
                        shutil.rmtree(child, ignore_errors=True)
                except FileNotFoundError:
                    pass

        for child in self.config.download_dir.iterdir():
            if child.is_file():
                try:
                    if child.stat().st_mtime < cutoff:
                        child.unlink(missing_ok=True)
                except OSError:
                    log.warning("Could not remove %s", child)
