from __future__ import annotations
import dataclasses
import json
import os
import time
from typing import Any

from .types import AuditEvent, AuditSink


def _today_stamp() -> str:
    return time.strftime("%Y-%m-%d")


def _json_default(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if hasattr(obj, "value"):
        return obj.value
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


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
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(json.dumps(_json_default(event), default=_json_default) + "\n")
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