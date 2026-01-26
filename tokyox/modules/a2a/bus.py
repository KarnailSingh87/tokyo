from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class A2AMessage:
    from_: str
    topic: str
    body: Any
    ts: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


HandlerFn = Callable[[A2AMessage], None]


class AgentBus:
    def __init__(self):
        self._subs: dict[str, list[Callable[[A2AMessage], None]]] = {}
        self._history: list[A2AMessage] = []

    def publish(self, from_: str, topic: str, body: Any) -> int:
        msg = A2AMessage(from_=from_, topic=topic, body=body)
        self._history.append(msg)
        if len(self._history) > 200:
            self._history.pop(0)
        delivered = 0
        for h in self._subs.get(topic, []):
            try:
                h(msg)
                delivered += 1
            except Exception:
                pass
        return delivered

    def subscribe(self, topic: str, handler: Callable[[A2AMessage], None]) -> Callable[[], None]:
        self._subs.setdefault(topic, []).append(handler)
        return lambda: self._subs[topic].remove(handler)

    def history(self, n: int = 20) -> list[A2AMessage]:
        return self._history[-n:]


from dataclasses import field