from __future__ import annotations
import re
import time
from typing import Any

from .types import (
    ActionRequest,
    AuditEvent,
    AuditSink,
    Decision,
    PermissionPolicy,
    PolicyRule,
    Verdict,
    new_id,
)


HARD_DENY_TERMINAL = re.compile(
    r"(rm\s+-rf\s+\/(?:\s|$)|sudo\s+rm\b|mkfs(\.\w+)?\s|dd\s+if=.*of=\/dev\/|shutdown\b|reboot\b|:\(\)\s*\{\s*:\|\:&\s*\}\s*;)"
)


class PermissionEngine:
    def __init__(self, policy: PermissionPolicy, sinks: list[AuditSink] | None = None):
        self.policy = policy
        self.rules = sorted(policy.rules, key=lambda r: -r.priority)
        self.sinks = sinks or []

    def add_sink(self, sink: AuditSink) -> None:
        self.sinks.append(sink)

    def evaluate(self, actor: str, req: ActionRequest) -> Decision:
        matched = self._match(req)
        verdict = matched.verdict if matched else self.policy.default_verdict
        rule_id = matched.id if matched else "default"
        reason = matched.reason if matched else "no rule matched; default verdict applied"

        if (
            req.category.value == "terminal"
            and isinstance(req.args, dict)
            and isinstance(req.args.get("command"), str)
            and HARD_DENY_TERMINAL.search(req.args["command"])
        ):
            verdict = Verdict.DENY
            rule_id = "hard-deny-destructive"
            reason = "matches built-in destructive command guardrail"

        decision = Decision(
            request_id=new_id("req"),
            tool=req.tool,
            verdict=verdict,
            rule_id=rule_id,
            reason=reason,
            requires_approval_token=verdict == Verdict.CONFIRM and req.risk_tier >= RiskTier.SYSTEM_AFFECTING,
        )

        event = AuditEvent(
            id=new_id("evt"),
            ts=decision.evaluated_at,
            actor=actor,
            request=req,
            decision=decision,
        )
        for sink in self.sinks:
            sink.record(event)
        return decision

    def _match(self, req: ActionRequest) -> PolicyRule | None:
        for rule in self.rules:
            has_criteria = rule.tools is not None or rule.categories is not None or rule.arg_regex is not None
            if not has_criteria:
                continue
            if rule.tools and req.tool not in rule.tools:
                continue
            if rule.categories and req.category not in rule.categories:
                continue
            if rule.arg_regex:
                for arg_name, pattern in rule.arg_regex.items():
                    raw = req.args.get(arg_name) if req.args else None
                    if not isinstance(raw, str) or not re.search(pattern, raw):
                        break
                else:
                    return rule
            return rule
        return None


def parse_policy(obj: dict[str, Any]) -> PermissionPolicy:
    if not isinstance(obj, dict):
        raise ValueError("policy must be dict")
    default = obj.get("defaultVerdict", "CONFIRM")
    if default not in ("ALLOW", "CONFIRM", "DENY"):
        raise ValueError("invalid defaultVerdict")
    rules = []
    for r in obj.get("rules", []):
        if not all(k in r for k in ("id", "priority", "verdict", "reason")):
            raise ValueError("rule missing required fields")
        rules.append(
            PolicyRule(
                id=r["id"],
                priority=int(r["priority"]),
                verdict=Verdict(r["verdict"]),
                reason=r["reason"],
                tools=r.get("tools"),
                categories=[ToolCategory(c) for c in r["categories"]] if r.get("categories") else None,
                arg_regex=r.get("argRegex"),
            )
        )
    return PermissionPolicy(version=obj.get("version", "0.1.0"), default_verdict=Verdict(default), rules=rules)


from .types import ToolCategory, RiskTier