import type { ModelRouter } from "../router/model-router.js";
import type { Orchestrator, ExecutionOutcome } from "./orchestrator.js";
import { simulation } from "../modules/simulation.js";

export interface GoalStepPlan {
  tool: string;
  args: Record<string, unknown>;
  purpose: string;
}

export interface StepOutcome {
  plan: GoalStepPlan;
  outcome: ExecutionOutcome;
}

export interface GoalRun {
  goal: string;
  actor: string;
  plan: GoalStepPlan[];
  steps: StepOutcome[];
  verification: { verdict: "pass" | "partial" | "fail"; notes: string };
  summary: string;
}

const MAX_STEPS = 5;

function heuristicPlan(goal: string): GoalStepPlan[] {
  const g = goal.toLowerCase();
  const steps: GoalStepPlan[] = [];
  if (/\b(read|open|show|summar)\b/.test(g)) {
    const keyword = g.replace(/^(read|open|show|summar|the|a|an|file|doc|ument)\s*/i, "").slice(0, 40);
    steps.push({ tool: "fs.search", args: { pattern: keyword }, purpose: "locate relevant workspace files" });
  }
  steps.push({ tool: "memory.set", args: { key: `goal:${Date.now() % 100000}`, value: goal }, purpose: "record directive in twin memory" });
  if (/\b(note|remind|remember)\b/.test(g)) {
    steps.push({ tool: "notify.send", args: { target: "log", message: goal }, purpose: "log reminder" });
  }
  return steps.slice(0, MAX_STEPS);
}

async function llmPlan(router: ModelRouter, toolsDesc: string, goal: string): Promise<GoalStepPlan[] | null> {
  try {
    const resp = await router.chat(
      ["openai:gpt-4o-mini", "openrouter:anthropic/claude-3.5-sonnet"],
      {
        messages: [
          { role: "system", content: `You are TOKYO-X planner. Output ONLY a JSON array (max ${MAX_STEPS}) of steps: [{"tool":"<tool>","args":{...},"purpose":"..."}]. Allowed tools:\n${toolsDesc}` },
          { role: "user", content: goal },
        ],
        temperature: 0.1,
        timeoutMs: 20_000,
      }
    );
    const m = resp.content.match(/\[[\s\S]*\]/);
    if (!m) return null;
    const arr = JSON.parse(m[0]) as GoalStepPlan[];
    if (!Array.isArray(arr)) return null;
    return arr.filter((s) => s && typeof s.tool === "string").slice(0, MAX_STEPS);
  } catch {
    return null;
  }
}

async function verifyRun(
  router: ModelRouter,
  goal: string,
  steps: StepOutcome[]
): Promise<{ verdict: "pass" | "partial" | "fail"; notes: string }> {
  const digest = steps
    .map((s, i) => `${i + 1}. ${s.plan.tool} → ${JSON.stringify({ status: s.outcome.status, error: s.outcome.error, result: s.outcome.result ? "ok" : undefined }).slice(0, 160)}`)
    .join("\n");
  try {
    const resp = await router.chat(
      ["openai:gpt-4o-mini", "openrouter:anthropic/claude-3.5-sonnet"],
      {
        messages: [
          { role: "system", content: "You verify task completion. Reply ONLY JSON {\"verdict\":\"pass|partial|fail\",\"notes\":\"...\"}" },
          { role: "user", content: `Goal: ${goal}\nSteps:\n${digest}` },
        ],
        temperature: 0,
        timeoutMs: 15_000,
      }
    );
    const m = resp.content.match(/\{[\s\S]*\}/);
    if (m) return JSON.parse(m[0]);
  } catch {
    // fall through to heuristic
  }
  const denied = steps.filter((s) => s.outcome.status === "denied").length;
  const errors = steps.filter((s) => s.outcome.status === "error").length;
  if (denied === steps.length) return { verdict: "fail", notes: "all steps denied" };
  if (denied > 0 || errors > 0) return { verdict: "partial", notes: `${denied} denied, ${errors} errors` };
  return { verdict: "pass", notes: "all steps executed" };
}

export class AgentLoop {
  constructor(
    private readonly router: ModelRouter,
    private readonly orchestrator: Orchestrator
  ) {}

  async runGoal(goal: string, actor = "kapil"): Promise<GoalRun> {
    const toolsDesc = this.orchestrator.tools.describeForLLM();
    let plan = simulation.enabled ? heuristicPlan(goal) : (await llmPlan(this.router, toolsDesc, goal)) ?? heuristicPlan(goal);
    const known = new Set(this.orchestrator.tools.list().map((t) => t.name));
    plan = plan.filter((s) => known.has(s.tool));
    if (plan.length === 0) plan = heuristicPlan(goal).filter((s) => known.has(s.tool));

    const steps: StepOutcome[] = [];
    for (const step of plan) {
      let outcome = await this.orchestrator.executeTool(actor, step.tool, step.args);
      if (outcome.status === "approval-required" && outcome.approval) {
        const resolved = await this.orchestrator.approvals?.waitResolved(outcome.approval.id, 120_000);
        if (resolved === null) {
          outcome = { ...outcome, status: "error", error: "approval timed out" };
        } else if (resolved?.approved) {
          outcome = await this.orchestrator.executeTool(actor, step.tool, step.args);
        } else {
          outcome = { ...outcome, status: "denied", error: "approval denied by kapil" };
        }
      } else if (outcome.status === "error") {
        outcome = await this.orchestrator.executeTool(actor, step.tool, step.args);
      }
      steps.push({ plan: step, outcome });
    }

    const verification = await verifyRun(this.router, goal, steps);
    const summary = `${goal} — ${verification.verdict} (${steps.length} steps)`;
    return { goal, actor, plan, steps, verification, summary };
  }
}