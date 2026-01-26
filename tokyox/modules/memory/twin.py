from __future__ import annotations
import json
import os
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class MemoryEntry:
    key: str
    value: str
    tags: list[str]
    ts: str


class TwinMemory:
    def __init__(self, directory: str):
        self._dir = directory
        self._entries: dict[str, MemoryEntry] = {}
        os.makedirs(directory, exist_ok=True)
        self._file = os.path.join(directory, "twin.jsonl")
        if os.path.exists(self._file):
            with open(self._file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                        self._entries[e["key"]] = MemoryEntry(**e)
                    except Exception:
                        continue

    def set(self, key: str, value: str, tags: list[str] | None = None) -> MemoryEntry:
        if not key.strip():
            raise ValueError("memory key required")
        entry = MemoryEntry(
            key=key[:120],
            value=str(value)[:8000],
            tags=(tags or [])[:8],
            ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self._entries[entry.key] = entry
        with open(self._file, "a") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
        return entry

    def get(self, key: str) -> MemoryEntry | None:
        return self._entries.get(key)

    def search(self, query: str, limit: int = 5) -> list[tuple[MemoryEntry, int]]:
        tokens = [t for t in query.lower().split() if t]
        scored: list[tuple[MemoryEntry, int]] = []
        for e in self._entries.values():
            score = 0
            hay = f"{e.key} {e.value}".lower()
            for t in tokens:
                if t in hay:
                    score += 1
            for tag in e.tags:
                if tag.lower() in tokens:
                    score += 2
            if score > 0:
                scored.append((e, score))
        scored.sort(key=lambda x: (-x[1], x[0].ts))
        return scored[:limit]

    def recent(self, n: int = 10) -> list[MemoryEntry]:
        return sorted(self._entries.values(), key=lambda e: e.ts, reverse=True)[:n]

    def __len__(self) -> int:
        return len(self._entries)