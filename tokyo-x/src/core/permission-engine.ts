import type { RiskTier, ToolCategory } from "./tool-schema.js";

export type Verdict = "ALLOW" | "CONFIRM" | "DENY";

export interface ActionRequest {
  tool: string;
  category: ToolCategory;
  riskTier: RiskTier;
  args?: Record<string, unknown>;
}

export interface Decision {
  requestId: string;
  tool: string;
  verdict: Verdict;
  ruleId: string;
  reason: string;
  requiresApprovalToken: boolean;
  evaluatedAt: string;
}

export interface ArgRegexMatcher {
  arg: string;
  pattern: string;
}

export interface PolicyRule {
  id: string;
  priority: number;
  verdict: Verdict;
  reason: string;
  tools?: string[];
  categories?: ToolCategory[];
  argRegex?: ArgRegexMatcher;
}

export interface PermissionPolicy {
  version: string;
  defaultVerdict: Verdict;
  rules: PolicyRule[];
}

export interface AuditEvent {
  id: string;
  ts: string;
  actor: string;
  request: ActionRequest;
  decision: Decision;
}

export interface AuditSink {
  record(event: AuditEvent): void;
}

let counter = 0;

function newId(prefix: string): string {
  counter += 1;
  return `${prefix}_${Date.now().toString(36)}_${counter.toString(36)}`;
}

const HARD_DENY_TERMINAL =
  /(rm\s+-rf\s+\/(?:\s|$)|sudo\s+rm\b|mkfs(\.\w+)?\s|dd\s+if=.*of=\/dev\/|shutdown\b|reboot\b|:\(\)\s*\{\s*:\|\:&\s*\}\s*;)/;

export class PermissionEngine {
  private rules: PolicyRule[];

  constructor(
    private readonly policy: PermissionPolicy,
    private sinks: AuditSink[] = []
  ) {
    this.rules = [...policy.rules].sort((a, b) => b.priority - a.priority);
  }

  addSink(sink: AuditSink): void {
    this.sinks.push(sink);
  }

  evaluate(actor: string, req: ActionRequest): Decision {
    const matched = this.match(req);
    let verdict = matched?.verdict ?? this.policy.defaultVerdict;
    let ruleId = matched?.id ?? "default";
    let reason = matched?.reason ?? "no rule matched; default verdict applied";

    if (
      req.category === "terminal" &&
      typeof req.args?.command === "string" &&
      HARD_DENY_TERMINAL.test(req.args.command)
    ) {
      verdict = "DENY";
      ruleId = "hard-deny-destructive";
      reason = "matches built-in destructive command guardrail";
    }

    const decision: Decision = {
      requestId: newId("req"),
      tool: req.tool,
      verdict,
      ruleId,
      reason,
      requiresApprovalToken: verdict === "CONFIRM" && req.riskTier >= 2,
      evaluatedAt: new Date().toISOString(),
    };

    const event: AuditEvent = {
      id: newId("evt"),
      ts: decision.evaluatedAt,
      actor,
      request: req,
      decision,
    };
    for (const sink of this.sinks) sink.record(event);
    return decision;
  }

  private match(req: ActionRequest): PolicyRule | undefined {
    return this.rules.find((rule) => {
      const hasCriteria =
        rule.tools !== undefined || rule.categories !== undefined || rule.argRegex !== undefined;
      if (!hasCriteria) return false;
      if (rule.tools && !rule.tools.includes(req.tool)) return false;
      if (rule.categories && !rule.categories.includes(req.category)) return false;
      if (rule.argRegex) {
        const raw = req.args?.[rule.argRegex.arg];
        if (typeof raw !== "string" || !new RegExp(rule.argRegex.pattern).test(raw)) return false;
      }
      return true;
    });
  }
}

export function parsePolicy(json: unknown): PermissionPolicy {
  const p = json as PermissionPolicy;
  if (
    !p ||
    typeof p !== "object" ||
    !Array.isArray(p.rules) ||
    (p.defaultVerdict !== "ALLOW" &&
      p.defaultVerdict !== "CONFIRM" &&
      p.defaultVerdict !== "DENY")
  ) {
    throw new Error("invalid permission policy document");
  }
  return p;
}
