from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from ..config import Config
from ..database import Database
from ..models import JobStatus
from ..services.validation import ValidationError, validate_file
from ..utils.security import new_job_id

log = logging.getLogger(__name__)


@dataclass
class RuntimeJob:
    job_id: str
    user_id: int
    chat_id: int
    operation: str
    message_id: int | None
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    inputs: list[Path] = field(default_factory=list)
    params: dict = field(default_factory=dict)
    retries: int = 0


Runner = Callable[[RuntimeJob, Callable[[int, str], Awaitable[None]]], Awaitable[list[Path]]]


class JobManager:
    on_progress: Callable[[RuntimeJob, int, str], Awaitable[None]] | None = None
    on_complete: Callable[[RuntimeJob, list], Awaitable[None]] | None = None
    on_failed: Callable[..., Awaitable[None]] | None = None

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.semaphore = asyncio.Semaphore(config.max_concurrent_jobs)
        self.runtime: dict[str, RuntimeJob] = {}
        self.user_active: dict[int, int] = {}
        self.queue_slots = asyncio.Semaphore(config.max_queue_size + config.max_concurrent_jobs)
        self._lock = asyncio.Lock()

    async def create(
        self,
        user_id: int,
        chat_id: int,
        operation: str,
        inputs: list[Path],
        params: dict,
        message_id: int | None,
        runner: Runner,
        retry_count: int = 0,
    ) -> RuntimeJob:
        async with self._lock:
            if self.user_active.get(user_id, 0) >= self.config.max_jobs_per_user:
                raise RuntimeError("You already have an active job.")
            if self.queue_slots.locked():
                raise RuntimeError("Queue is full. Try again shortly.")
            await self.queue_slots.acquire()
            job_id = new_job_id()
            job_dir = self.config.job_data_dir / job_id / "input"
            job_dir.mkdir(parents=True, exist_ok=True)
            copied: list[Path] = []
            for source in inputs:
                dest = job_dir / source.name
                shutil.copy2(source, dest)
                copied.append(dest)
            await self.db.create_job(job_id, user_id, chat_id, operation, {"params": params})
            job = RuntimeJob(
                job_id=job_id,
                user_id=user_id,
                chat_id=chat_id,
                operation=operation,
                message_id=message_id,
                inputs=copied,
                params=params,
                retries=retry_count,
            )
            self.runtime[job_id] = job
            self.user_active[user_id] = self.user_active.get(user_id, 0) + 1
            job.task = asyncio.create_task(self._execute(job, runner), name=f"job-{job_id}")
            return job

    async def _execute(self, job: RuntimeJob, runner: Runner) -> None:
        async def progress(value: int, stage: str) -> None:
            if job.cancel.is_set():
                raise asyncio.CancelledError
            await self.db.set_job(job.job_id, status=JobStatus.PROCESSING, progress=value)
            if self.on_progress:
                await self.on_progress(job, value, stage)

        try:
            await self.db.set_job(job.job_id, status=JobStatus.PROCESSING, progress=1)
            async with self.semaphore:
                if job.cancel.is_set():
                    raise asyncio.CancelledError
                outputs = await asyncio.wait_for(
                    runner(job, progress), timeout=self.config.provider_timeout * 10
                )
                if not outputs:
                    raise ValidationError("No output produced.")
                valid = []
                for path in outputs:
                    checked = validate_file(path, self.config)
                    valid.append(checked)
                    await self.db.add_result(
                        job.job_id, path, checked.media_type, path.name, checked.size_bytes
                    )
                await self.db.set_job(
                    job.job_id, status=JobStatus.COMPLETED, progress=100, output_count=len(valid)
                )
                if self.on_complete:
                    await self.on_complete(job, valid)
        except asyncio.CancelledError:
            await self.db.set_job(job.job_id, status=JobStatus.CANCELLED, error="Cancelled")
            if self.on_failed:
                await self.on_failed(job, "Cancelled.")
        except Exception as exc:
            log.exception("Job %s failed", job.job_id)
            await self.db.set_job(job.job_id, status=JobStatus.FAILED, error=str(exc))
            if self.on_failed:
                await self.on_failed(job, str(exc), retryable=not isinstance(exc, ValidationError))
        finally:
            async with self._lock:
                self.runtime.pop(job.job_id, None)
                self.user_active[job.user_id] = max(0, self.user_active.get(job.user_id, 1) - 1)
            self.queue_slots.release()

    async def cancel(self, job_id: str, user_id: int) -> bool:
        job = self.runtime.get(job_id)
        if not job or job.user_id != user_id:
            return False
        job.cancel.set()
        return True

    async def cancel_all(self, user_id: int) -> int:
        count = 0
        for job in list(self.runtime.values()):
            if job.user_id == user_id:
                job.cancel.set()
                count += 1
        return count

    async def shutdown(self) -> None:
        jobs = list(self.runtime.values())
        for job in jobs:
            job.cancel.set()
        tasks = [j.task for j in jobs if j.task]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
