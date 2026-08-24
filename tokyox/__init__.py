from __future__ import annotations
"""TOKYO-X Python integration for Mark-LI. Exposes a unified async interface."""

import os
import json
import time
import uuid
from pathlib import Path
from typing import Any

from tokyox.core.types import ToolDefinition, ToolCategory, RiskTier, JsonSchemaField
from tokyox.core.permission_engine import PermissionEngine, parse_policy
from tokyox.core.tool_schema import ToolRegistry
from tokyox.core.orchestrator import Orchestrator, ExecutionOutcome
from tokyox.core.approvals import PendingApprovals
from tokyox.core.audit import FileAuditSink
from tokyox.core.agent_loop import AgentLoop, GoalRun
from tokyox.router.model_router import (
    ModelRouter,
    create_production_router,
    ChatMessage,
    ChatRequest,
)
from tokyox.tools import create_tool_executors, TOOL_DEFINITIONS
from tokyox.voice.tts import ElevenLabsTTS, load_voices
from tokyox.voice.stt import create_transcriber
from tokyox.modules.memory.twin import TwinMemory
from tokyox.modules.jobs.task_manager import TaskManager
from tokyox.modules.a2a.bus import AgentBus
from tokyox.modules.proactive.watcher import ProactiveWatcher
from tokyox.modules.skills.registry import SkillRegistry
from tokyox.modules.cost.dashboard import CostDashboard
from tokyox.modules.simulation import simulation
from tokyox.phone.hub import ApprovalHub


class TokyoX:
    def __init__(self, base_dir: Path):
        self._base = base_dir
        self._config = base_dir / "config"
        self._logs = base_dir / "logs"
        self._workspace = base_dir / "workspace"
        self._workspace.mkdir(exist_ok=True)
        self._logs.mkdir(exist_ok=True)

        # Load configs
        with open(self._config / "managers.json") as f:
            self._managers = json.load(f)
        with open(self._config / "permissions.json") as f:
            self._policy = parse_policy(json.load(f))

        # Core
        self._audit_sink = FileAuditSink(self._logs / "audit")
        self._permission_engine = PermissionEngine(self._policy, [self._audit_sink])

        # Model router
        self._router = create_production_router(str(self._logs), str(self._config))

        # Approvals
        approval_secret = os.environ.get("TOKYOX_APPROVAL_TOKEN_SECRET", "dev-secret-change-me")
        self._approvals = PendingApprovals(approval_secret)

        # Orchestrator
        self._orch = Orchestrator(
            managers=self._managers,
            permissions=self._permission_engine,
            router=self._router,
            approvals=self._approvals,
        )

        # Register all tool definitions
        for td in TOOL_DEFINITIONS:
            self._orch.tools.register(td)

        # Tool executors
        self._twin = TwinMemory(str(self._logs / "twin"))
        execs = create_tool_executors(
            workspace_root=str(self._workspace),
            screen_dir=str(self._logs / "screens"),
            twin=self._twin,
        )
        for name, fn in execs.items():
            self._orch.register_executor(name, fn)

        # Voice
        self._voices = load_voices(str(self._config / "voices.json"))
        self._tts = ElevenLabsTTS(self._voices)
        self._stt = create_transcriber()

        # Modules
        self._bus = AgentBus()
        self._watcher = ProactiveWatcher(self._bus, self._twin)
        self._skills = SkillRegistry(str(self._config / "skills.json"))
        self._jobs = TaskManager(str(self._logs))
        self._cost_dashboard = CostDashboard(self._router.logger)

        # Register goal runner
        self._jobs.register("goal", self._goal_runner)

        # Agent loop
        self._agent_loop = AgentLoop(self._router, self._orch)

        # Phone hub
        self._pair_token = uuid.uuid4().hex[:16]
        self._hub = ApprovalHub(self._pair_token, self._approvals.resolve)

    @property
    def orchestrator(self) -> Orchestrator:
        return self._orch

    @property
    def router(self):
        return self._router

    @property
    def approvals(self):
        return self._approvals

    @property
    def twin(self) -> TwinMemory:
        return self._twin

    @property
    def pair_token(self) -> str:
        return self._pair_token

    @property
    def hub(self) -> ApprovalHub:
        return self._hub

    async def execute_tool(self, actor: str, tool: str, args: dict) -> ExecutionOutcome:
        return await self._orch.execute_tool(actor, tool, args)

    async def run_goal(self, goal: str, actor: str = "kapil") -> GoalRun:
        return await self._agent_loop.run_goal(goal, actor)

    async def _goal_runner(self, payload: dict, job, report):
        return await self.run_goal(payload.get("goal", ""), payload.get("actor", "kapil"))

    async def synthesize(self, text: str, preset: str | None = None):
        return await self._tts.synthesize(text, preset)

    async def transcribe(self, audio: bytes, mime: str):
        return await self._stt.transcribe(audio, mime)

    def get_voice_presets(self):
        return {
            "presets": [{"id": p.id, "name": p.name, "description": p.description} for p in self._tts.presets()],
            "default": self._tts.default_preset().id,
            "tts_available": self._tts.is_configured(),
        }

    def status(self):
        return {
            "phase": 8,
            "pairing_code": "-".join(self._pair_token[i:i+4] for i in range(0, 16, 4)).upper(),
            "router": self._router.status(),
            "pending_approvals": len(self._approvals.list()),
            "jobs": self._jobs.stats,
        }


def create_tokyox(base_dir: str | Path = None) -> TokyoX:
    base = Path(base_dir) if base_dir else Path(__file__).resolve().parents[2]
    return TokyoX(base)