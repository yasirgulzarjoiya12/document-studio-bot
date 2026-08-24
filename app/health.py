from __future__ import annotations

import asyncio
import logging
import time
from aiohttp import web

log = logging.getLogger(__name__)


class HealthServer:
    """Minimal always-on health server for platform probes (Back4App/Docker/K8s)."""

    def __init__(self, port: int, started: float | None = None, db=None):
        self.port = port
        self.started = started or time.time()
        self.db = db
        self.runner: web.AppRunner | None = None

    async def _health(self, request: web.Request) -> web.Response:
        database = "unknown"
        if self.db is not None:
            try:
                async def _ping() -> None:
                    conn = self.db._db()
                    cur = await conn.execute("SELECT 1")
                    await cur.fetchone()
                    await cur.close()

                await asyncio.wait_for(_ping(), timeout=1.5)
                database = "ok"
            except Exception:
                database = "error"
        payload = {
            "status": "ok",
            "database": database,
            "bot_process": "running",
            "uptime_seconds": int(time.time() - self.started),
            "version": "1.0.0",
        }
        # Always 200 so platform probes pass while the process is alive.
        return web.json_response(payload, status=200)

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._health)
        app.router.add_get("/", self._health)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await site.start()
        log.info("Health endpoint ready at http://0.0.0.0:%s/health", self.port)

    def attach_db(self, db) -> None:
        self.db = db

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
