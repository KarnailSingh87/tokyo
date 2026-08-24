from __future__ import annotations
import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


class RiskTier(int, enum.Enum):
    READ_ONLY = 0
    REVERSIBLE_WRITE = 1
    SYSTEM_AFFECTING = 2
    NEVER_AUTO = 3


class ToolCategory(str, enum.Enum):
    FILE = "file"
    TERMINAL = "terminal"
    BROWSER = "browser"
    SCREEN = "screen"
    VOICE = "voice"
    MEMORY = "memory"
    NETWORK = "network"
    NOTIFY = "notify"


class Verdict(str, enum.Enum):
    ALLOW = "ALLOW"
    CONFIRM = "CONFIRM"
    DENY = "DENY"


@dataclass
class JsonSchemaField:
    type: str
    description: str | None = None
    enum: list[str | int] | None = None
    items: JsonSchemaField | None = None
    properties: dict[str, JsonSchemaField] | None = None
    required: list[str] | None = None


@dataclass
class ToolDefinition:
    name: str
    version: str
    description: str
    category: ToolCategory
    risk_tier: RiskTier
    enabled: bool = True
    input_schema: JsonSchemaField | None = None
    output_schema: JsonSchemaField | None = None


@dataclass
class ActionRequest:
    tool: str
    category: ToolCategory
    risk_tier: RiskTier
    args: dict[str, Any] | None = None


@dataclass
class Decision:
    request_id: str
    tool: str
    verdict: Verdict
    rule_id: str
    reason: str
    requires_approval_token: bool
    evaluated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass
class PolicyRule:
    id: str
    priority: int
    verdict: Verdict
    reason: str
    tools: list[str] | None = None
    categories: list[ToolCategory] | None = None
    arg_regex: dict[str, str] | None = None


@dataclass
class PermissionPolicy:
    version: str
    default_verdict: Verdict
    rules: list[PolicyRule]


@dataclass
class AuditEvent:
    id: str
    ts: str
    actor: str
    request: ActionRequest
    decision: Decision


class AuditSink:
    def record(self, event: AuditEvent) -> None:
        raise NotImplementedError


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]


def new_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"