import type { ManagerRegistry } from "../agents/managers.js";
import type { ModelRouter } from "../router/model-router.js";
import type { PendingApprovals, PendingHandle } from "./approvals.js";
import { PermissionEngine, type Decision, type ActionRequest } from "./permission-engine.js";
export type { Decision } from "./permission-engine.js";
import { ToolRegistry } from "./tool-schema.js";

export type OrchestratorStatus =
  | "idle"
  | "planning"
  | "awaiting_approval"
  | "executing"
  | "verifying"
  | "error";

export interface GoalContext {
  actor: string;
  goal: string;
}

export type ExecutorFn = (args: Record<string, unknown>, ctx: { actor: string }) => Promise<unknown>;

export interface ExecutionOutcome {
  status: "executed" | "approval-required" | "denied" | "invalid" | "unknown-tool" | "error";
  decision?: Decision;
  approval?: PendingHandle;
  result?: unknown;
  error?: string;
}

export class Orchestrator {
  readonly tools = new ToolRegistry();
  readonly executors = new Map<string, ExecutorFn>();
  status: OrchestratorStatus = "idle";

  constructor(
    readonly managers: ManagerRegistry,
    readonly permissions: PermissionEngine,
    readonly router?: ModelRouter,
    readonly approvals?: PendingApprovals
  ) {}

  registerExecutor(name: string, fn: ExecutorFn): void {
    this.executors.set(name, fn);
  }

  authorize(actor: string, req: ActionRequest): Decision {
    return this.permissions.evaluate(actor, req);
  }

  async executeTool(actor: string, toolName: string, args: Record<string, unknown>): Promise<ExecutionOutcome> {
    const tool = this.tools.get(toolName);
    if (!tool || !tool.enabled) return { status: "unknown-tool", error: `unknown or disabled tool: ${toolName}` };

    const validation = this.tools.validateInput(toolName, args);
    if (!validation.ok) return { status: "invalid", error: validation.errors.join("; ") };

    const req: ActionRequest = { tool: toolName, category: tool.category, riskTier: tool.riskTier, args };
    const decision = this.authorize(actor, req);

    if (decision.verdict === "DENY") return { status: "denied", decision };

    if (decision.verdict === "CONFIRM") {
      const handle = this.approvals?.create(decision, args, tool.category, tool.riskTier);
      return { status: "approval-required", decision, approval: handle };
    }

    const executor = this.executors.get(toolName);
    if (!executor) return { status: "error", decision, error: `no executor registered for ${toolName}` };

    try {
      const result = await executor(args, { actor });
      return { status: "executed", decision, result };
    } catch (err) {
      return { status: "error", decision, error: err instanceof Error ? err.message : String(err) };
    }
  }

  async runGoal(_ctx: GoalContext): Promise<never> {
    throw new Error("use AgentLoop.runGoal instead");
  }
}