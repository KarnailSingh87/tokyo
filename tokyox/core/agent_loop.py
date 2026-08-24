from __future__ import annotations
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .orchestrator import Orchestrator, ExecutionOutcome
from ..router import ModelRouter
from ..modules.simulation import simulation


@dataclass
class GoalStepPlan:
    tool: str
    args: dict[str, Any]
    purpose: str


@dataclass
class StepOutcome:
    plan: GoalStepPlan
    outcome: ExecutionOutcome


@dataclass
class GoalRun:
    goal: str
    actor: str
    plan: list[GoalStepPlan]
    steps: list[StepOutcome]
    verification: dict[str, str]
    summary: str


MAX_STEPS = 5


def heuristic_plan(goal: str) -> list[GoalStepPlan]:
    g = goal.lower()
    steps: list[GoalStepPlan] = []
    if re.search(r"\b(read|open|show|summar)\b", g):
        keyword = re.sub(r"^(read|open|show|summar|the|a|an|file|doc|ument)\s*", "", g).strip()[:40]
        steps.append(GoalStepPlan("fs.search", {"pattern": keyword}, "locate relevant workspace files"))
    steps.append(GoalStepPlan("memory.set", {"key": f"goal:{int(time.time() * 1000) % 100000}", "value": goal}, "record directive in twin memory"))
    if re.search(r"\b(note|remind|remember)\b", g):
        steps.append(GoalStepPlan("notify.send", {"target": "log", "message": goal}, "log reminder"))
    return steps[:MAX_STEPS]


async def llm_plan(router: ModelRouter, tools_desc: str, goal: str) -> list[GoalStepPlan] | None:
    try:
        from ..router.model_router import ChatMessage, ChatRequest
        resp = await router.chat(
            ["openai:gpt-4o-mini", "openrouter:anthropic/claude-3.5-sonnet"],
            ChatRequest(
                messages=[
                    ChatMessage(role="system", content=f"You are TOKYO-X planner. Output ONLY a JSON array (max {MAX_STEPS}) of steps: [{{\"tool\":\"<tool>\",\"args\":{{...}},\"purpose\":\"...\"}}]. Allowed tools:\n{tools_desc}"),
                    ChatMessage(role="user", content=goal),
                ],
                temperature=0.1,
                timeout_ms=20_000,
            ),
        )
        m = re.search(r"\[[\s\S]*\]", resp.content)
        if not m:
            return None
        arr = json.loads(m.group(0))
        if not isinstance(arr, list):
            return None
        return [GoalStepPlan(**s) for s in arr if s and isinstance(s.get("tool"), str)][:MAX_STEPS]
    except Exception:
        return None


async def verify_run(router: ModelRouter, goal: str, steps: list) -> dict[str, str]:
    digest = "\n".join(f"{i+1}. {s.plan.tool} → {str(s.outcome.status)[:160]}" for i, s in enumerate(steps))
    try:
        from ..router.model_router import ChatMessage, ChatRequest
        resp = await router.chat(
            ["openai:gpt-4o-mini", "openrouter:anthropic/claude-3.5-sonnet"],
            ChatRequest(
                messages=[
                    ChatMessage(role="system", content='You verify task completion. Reply ONLY JSON {"verdict":"pass|partial|fail","notes":"..."}'),
                    ChatMessage(role="user", content=f"Goal: {goal}\nSteps:\n{digest}"),
                ],
                temperature=0.0,
                timeout_ms=15_000,
            ),
        )
        m = re.search(r"\{[\s\S]*\}", resp.content)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    denied = sum(1 for s in steps if s.outcome.status == "denied")
    errors = sum(1 for s in steps if s.outcome.status == "error")
    if denied == len(steps):
        return {"verdict": "fail", "notes": "all steps denied"}
    if denied > 0 or errors > 0:
        return {"verdict": "partial", "notes": f"{denied} denied, {errors} errors"}
    return {"verdict": "pass", "notes": "all steps executed"}


class AgentLoop:
    def __init__(self, router: ModelRouter, orchestrator: Orchestrator):
        self._router = router
        self._orch = orchestrator

    async def run_goal(self, goal: str, actor: str = "kapil") -> GoalRun:
        tools_desc = self._orch.tools.describe_for_llm()
        plan = simulation["enabled"] and heuristic_plan(goal) or (await llm_plan(self._router, tools_desc, goal)) or heuristic_plan(goal)
        known = {t.name for t in self._orch.tools.list()}
        plan = [s for s in plan if s.tool in known]
        if not plan:
            plan = [s for s in heuristic_plan(goal) if s.tool in known]

        steps: list = []
        for step in plan:
            outcome = await self._orch.execute_tool(actor, step.tool, step.args)
            if outcome.status == "approval-required" and outcome.approval:
                resolved = await self._orch.approvals.wait_resolved(outcome.approval.id, 120_000) if self._orch.approvals else None
                if resolved is None:
                    outcome = ExecutionOutcome("error", outcome.decision, error="approval timed out")
                elif resolved.get("approved"):
                    outcome = await self._orch.execute_tool(actor, step.tool, step.args)
                else:
                    outcome = ExecutionOutcome("denied", outcome.decision, error="approval denied by kapil")
            elif outcome.status == "error":
                outcome = await self._orch.execute_tool(actor, step.tool, step.args)
            steps.append(type("StepOutcome", (), {"plan": step, "outcome": outcome})())

        verification = await verify_run(self._router, goal, steps)
        summary = f"{goal} — {verification.get('verdict', 'unknown')} ({len(steps)} steps)"
        return GoalRun(goal=goal, actor=actor, plan=plan, steps=steps, verification=verification, summary=summary)