from __future__ import annotations
import time
from typing import Any

from ..a2a.bus import AgentBus
from ..memory.twin import TwinMemory


class ProactiveWatcher:
    def __init__(self, bus: AgentBus, twin: TwinMemory, interval_sec: int = 60):
        self._bus = bus
        self._twin = twin
        self._interval = interval_sec
        self._enabled = False
        self._task: asyncio.Task | None = None
        self._last_suggestions: list[str] = []

    def start(self) -> None:
        if self._enabled:
            return
        self._enabled = True
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._enabled = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while self._enabled:
            try:
                self._tick()
            except Exception:
                pass
            await asyncio.sleep(self._interval)

    def _tick(self) -> None:
        recent = self._twin.recent(3)
        context = " | ".join(e.value[:120] for e in recent) if recent else "idle"
        hour = time.localtime().tm_hour
        greet = "Morning" if hour < 12 else "Afternoon" if hour < 18 else "Evening"
        text = f"{greet} scan: {context}. Suggested next: review inbox, run tests, backup workspace."
        self._bus.publish("tokyo-x", "proactive.suggestion", {"text": text})
        self._last_suggestions.insert(0, text)
        if len(self._last_suggestions) > 10:
            self._last_suggestions.pop()

    def suggestions(self, n: int = 5) -> list[str]:
        return self._last_suggestions[:n]


import asyncio