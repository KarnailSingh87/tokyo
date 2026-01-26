from __future__ import annotations
import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from ..memory.twin import TwinMemory


@dataclass
class Job:
    id: str
    kind: str
    payload: Any
    status: Literal["queued", "running", "done", "failed", "cancelled"] = "queued"
    progress: int = 0
    result: Any = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    started_at: str | None = None
    finished_at: str | None = None


RunnerFn = Callable[[Any, Job, Callable[[int], None]], Awaitable[Any]]


class TaskManager:
    def __init__(self, event_dir: str, concurrency: int = 2):
        self._event_dir = event_dir
        self._concurrency = concurrency
        self._jobs: dict[str, Job] = {}
        self._queue: list[str] = []
        self._runners: dict[str, RunnerFn] = {}
        self._active = 0
        self._pump_task: asyncio.Task | None = None
        os.makedirs(event_dir, exist_ok=True)
        self._events_file = os.path.join(event_dir, "jobs.jsonl")

    def register(self, kind: str, runner: RunnerFn) -> None:
        self._runners[kind] = runner

    def submit(self, kind: str, payload: Any) -> Job:
        if kind not in self._runners:
            raise ValueError(f"no runner registered for kind '{kind}'")
        job = Job(
            id=f"job_{uuid.uuid4().hex[:10]}",
            kind=kind,
            payload=payload,
        )
        self._jobs[job.id] = job
        self._queue.append(job.id)
        self._event(job, "queued")
        self._pump()
        return job

    def cancel(self, id_: str) -> bool:
        job = self._jobs.get(id_)
        if not job:
            return False
        if job.status == "queued":
            self._queue = [j for j in self._queue if j != id_]
            job.status = "cancelled"
            job.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._event(job, "cancelled")
            return True
        return False

    def get(self, id_: str) -> Job | None:
        return self._jobs.get(id_)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    @property
    def stats(self) -> dict[str, int]:
        all_jobs = list(self._jobs.values())
        return {
            "total": len(all_jobs),
            "active": sum(1 for j in all_jobs if j.status == "running"),
            "queued": sum(1 for j in all_jobs if j.status == "queued"),
        }

    def _pump(self) -> None:
        if self._pump_task and not self._pump_task.done():
            return
        self._pump_task = asyncio.create_task(self._pump_loop())

    async def _pump_loop(self) -> None:
        while self._active < self._concurrency and self._queue:
            id_ = self._queue.pop(0)
            job = self._jobs.get(id_)
            if not job or job.status != "queued":
                continue
            await self._run(job)

    async def _run(self, job: Job) -> None:
        runner = self._runners.get(job.kind)
        if not runner:
            job.status = "failed"
            job.error = "runner vanished"
            self._event(job, "failed")
            return
        self._active += 1
        job.status = "running"
        job.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._event(job, "started")
        try:
            job.result = await runner(job.payload, job, lambda p: setattr(job, "progress", max(0, min(100, p))))
            job.progress = 100
            job.status = "done"
        except Exception as err:
            job.status = "failed"
            job.error = str(err)
        finally:
            job.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._active -= 1
            self._event(job, job.status)
            self._pump()

    def _event(self, job: Job, phase: str) -> None:
        line = json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "phase": phase,
            "id": job.id,
            "kind": job.kind,
            "status": job.status,
            "progress": job.progress,
        }) + "\n"
        try:
            with open(self._events_file, "a") as f:
                f.write(line)
        except Exception:
            pass