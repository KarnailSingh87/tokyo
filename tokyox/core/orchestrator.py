from __future__ import annotations
from typing import Any, Callable, Awaitable

from .types import Decision, ToolDefinition, RiskTier, ToolCategory
from .tool_schema import ToolRegistry
from .permission_engine import PermissionEngine
from .approvals import PendingApprovals, PendingHandle
from ..router import ModelRouter


ExecutorFn = Callable[[dict[str, Any], dict[str, str]], Awaitable[Any]]


class ExecutionOutcome:
    def __init__(
        self,
        status: Literal["executed", "approval-required", "denied", "invalid", "unknown-tool", "error"],
        decision: Decision | None = None,
        approval: PendingHandle | None = None,
        result: Any = None,
        error: str | None = None,
    ):
        self.status = status
        self.decision = decision
        self.approval = approval
        self.result = result
        self.error = error


class Orchestrator:
    def __init__(
        self,
        managers: Any,  # ManagerRegistry
        permissions: PermissionEngine,
        router: ModelRouter | None = None,
        approvals: PendingApprovals | None = None,
    ):
        self.tools = ToolRegistry()
        self._executors: dict[str, ExecutorFn] = {}
        self.managers = managers
        self.permissions = permissions
        self.router = router
        self.approvals = approvals
        self.status: Literal["idle", "planning", "awaiting_approval", "executing", "verifying", "error"] = "idle"

    def register_executor(self, name: str, fn: ExecutorFn) -> None:
        self._executors[name] = fn

    def authorize(self, actor: str, req) -> Decision:
        return self.permissions.evaluate(actor, req)

    async def execute_tool(self, actor: str, tool_name: str, args: dict[str, Any]) -> ExecutionOutcome:
        tool = self.tools.get(tool_name)
        if not tool or not tool.enabled:
            return ExecutionOutcome("unknown-tool", error=f"unknown or disabled tool: {tool_name}")

        validation = self.tools.validate_input(tool_name, args)
        if not validation.ok:
            return ExecutionOutcome("invalid", error="; ".join(validation.errors))

        req = type("ActionRequest", (), {
            "tool": tool_name,
            "category": tool.category,
            "risk_tier": tool.risk_tier,
            "args": args,
        })()
        decision = self.authorize(actor, req)

        if decision.verdict.value == "DENY":
            return ExecutionOutcome("denied", decision=decision)

        if decision.verdict.value == "CONFIRM":
            handle = self.approvals.create(decision, args, tool.category.value, tool.risk_tier.value) if self.approvals else None
            return ExecutionOutcome("approval-required", decision=decision, approval=handle)

        executor = self._executors.get(tool_name)
        if not executor:
            return ExecutionOutcome("error", decision=decision, error=f"no executor registered for {tool_name}")

        try:
            result = await executor(args, {"actor": actor})
            return ExecutionOutcome("executed", decision=decision, result=result)
        except Exception as err:
            return ExecutionOutcome("error", decision=decision, error=str(err))