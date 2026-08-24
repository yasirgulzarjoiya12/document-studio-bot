from __future__ import annotations

import asyncio
import logging
import time
from aiohttp import web

from .database import Database


log = logging.getLogger(__name__)


class HealthServer:
    def __init__(self, db: Database, port: int, started: float):
        self.db = db
        self.port = port
        self.started = started
        self.runner: web.AppRunner | None = None

    async def _health(self, request: web.Request) -> web.Response:
        database = "ok"
        try:
            # Bound DB check so a stuck connection cannot hang the health probe.
            async def _ping() -> None:
                db = self.db._db()
                cur = await db.execute("SELECT 1")
                await cur.fetchone()
                await cur.close()

            await asyncio.wait_for(_ping(), timeout=2.0)
        except Exception as exc:
            database = "error"
            log.debug("Health DB check failed: %s", exc)

        # Always return 200 while the process is alive. Docker/K8s only need to
        # know the process is up; detailed status is in the JSON body. Returning
        # 503 caused containers to be killed after a few failed probes (~1 min).
        payload = {
            "status": "ok" if database == "ok" else "degraded",
            "database": database,
            "bot_process": "running",
            "uptime_seconds": int(time.time() - self.started),
            "version": "1.0.0",
        }
        return web.json_response(payload, status=200)

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._health)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await site.start()
        log.info("Health endpoint ready at http://0.0.0.0:%s/health", self.port)

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
