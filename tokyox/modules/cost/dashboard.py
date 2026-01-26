from __future__ import annotations
from typing import Any

from ...router import RouterLogger


class CostDashboard:
    def __init__(self, logger: RouterLogger):
        self._logger = logger

    def summary(self) -> dict[str, Any]:
        totals = self._logger.stats.__dict__.copy()
        by_model: dict[str, dict[str, Any]] = {}
        recent: list[dict[str, Any]] = []

        entries = self._logger.tail_lines(500)
        for e in entries:
            if e.event != "response":
                continue
            model = e.model or "unknown"
            prov = e.provider or "unknown"
            cost = e.cost_usd or 0.0
            key = f"{prov}:{model}"
            if key not in by_model:
                by_model[key] = {"calls": 0, "in": 0, "out": 0, "cost_usd": 0.0}
            by_model[key]["calls"] += 1
            by_model[key]["in"] += e.prompt_tokens or 0
            by_model[key]["out"] += e.completion_tokens or 0
            by_model[key]["cost_usd"] += cost
            recent.append({"ts": e.ts, "provider": prov, "model": model, "cost_usd": cost})

        return {"totals": totals, "by_model": by_model, "recent": recent[-20:]}