from __future__ import annotations
import json
import os
import time
from typing import Any

from .types import AuditEvent, AuditSink


def _today_stamp() -> str:
    return time.strftime("%Y-%m-%d")


class FileAuditSink(AuditSink):
    def __init__(self, directory: str, console_echo: bool = False):
        self._dir = directory
        self._console_echo = console_echo
        os.makedirs(directory, exist_ok=True)

    @property
    def _file(self) -> str:
        return os.path.join(self._dir, f"audit-{_today_stamp()}.jsonl")

    def record(self, event: AuditEvent) -> None:
        try:
            with open(self._file, "a") as f:
                f.write(json.dumps(event.__dict__) + "\n")
        except Exception:
            if self._console_echo:
                print("[audit] write failed")
        if self._console_echo:
            print(f"[audit] {event.decision.verdict.value} {event.decision.tool}")

    def tail(self, n: int) -> list[AuditEvent]:
        try:
            with open(self._file) as f:
                lines = f.read().splitlines()
        except Exception:
            return []
        return [AuditEvent(**json.loads(l)) for l in lines[-n:] if l.strip()]


def append_system_event(directory: str, type_: str, payload: Any) -> None:
    os.makedirs(directory, exist_ok=True)
    line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "type": type_, "payload": payload}) + "\n"
    with open(os.path.join(directory, f"events-{_today_stamp()}.jsonl"), "a") as f:
        f.write(line)