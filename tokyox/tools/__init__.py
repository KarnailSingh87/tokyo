from __future__ import annotations
import time
from typing import Any, Awaitable, Callable

from ..core.types import ToolDefinition, ToolCategory, RiskTier, JsonSchemaField
from .file_tools import make_sandbox, TOOL_DEFINITIONS_FILE
from .terminal_tools import make_terminal_tool
from .browser_tools import make_browser_tools
from .screen_tools import make_screen_tools


_memory_store: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


TOOL_DEFINITIONS: list[ToolDefinition] = [
    *TOOL_DEFINITIONS_FILE,
    ToolDefinition(
        name="terminal.exec",
        version="0.1.0",
        description="Run a shell command with timeout and output capture",
        category=ToolCategory.TERMINAL,
        risk_tier=RiskTier.SYSTEM_AFFECTING,
        input_schema=JsonSchemaField(type="object", required=["command"], properties={"command": JsonSchemaField(type="string"), "timeoutMs": JsonSchemaField(type="number")}),
    ),
    ToolDefinition(
        name="browser.open",
        version="0.1.0",
        description="Open a URL and return title/status",
        category=ToolCategory.BROWSER,
        risk_tier=RiskTier.REVERSIBLE_WRITE,
        input_schema=JsonSchemaField(type="object", required=["url"], properties={"url": JsonSchemaField(type="string")}),
    ),
    ToolDefinition(
        name="browser.search",
        version="0.1.0",
        description="Search the web via DuckDuckGo HTML",
        category=ToolCategory.BROWSER,
        risk_tier=RiskTier.REVERSIBLE_WRITE,
        input_schema=JsonSchemaField(type="object", required=["query"], properties={"query": JsonSchemaField(type="string")}),
    ),
    ToolDefinition(
        name="browser.act",
        version="0.1.0",
        description="Automated browser actions (planned)",
        category=ToolCategory.BROWSER,
        risk_tier=RiskTier.SYSTEM_AFFECTING,
        input_schema=JsonSchemaField(type="object", properties={"script": JsonSchemaField(type="string")}),
    ),
    ToolDefinition(
        name="screen.capture",
        version="0.1.0",
        description="Capture a screenshot of a display",
        category=ToolCategory.SCREEN,
        risk_tier=RiskTier.SYSTEM_AFFECTING,
        input_schema=JsonSchemaField(type="object", required=[], properties={"display": JsonSchemaField(type="number")}),
    ),
    ToolDefinition(
        name="screen.read",
        version="0.1.0",
        description="Read screen metadata (placeholder)",
        category=ToolCategory.SCREEN,
        risk_tier=RiskTier.REVERSIBLE_WRITE,
        input_schema=JsonSchemaField(type="object", required=[], properties={"display": JsonSchemaField(type="number")}),
    ),
    ToolDefinition(
        name="memory.get",
        version="0.1.0",
        description="Get a value from the digital twin memory",
        category=ToolCategory.MEMORY,
        risk_tier=RiskTier.READ_ONLY,
        input_schema=JsonSchemaField(type="object", required=["key"], properties={"key": JsonSchemaField(type="string")}),
    ),
    ToolDefinition(
        name="memory.set",
        version="0.1.0",
        description="Set a value in the digital twin memory",
        category=ToolCategory.MEMORY,
        risk_tier=RiskTier.READ_ONLY,
        input_schema=JsonSchemaField(type="object", required=["key", "value"], properties={"key": JsonSchemaField(type="string"), "value": JsonSchemaField(type="string"), "tags": JsonSchemaField(type="array", items=JsonSchemaField(type="string"))}),
    ),
    ToolDefinition(
        name="voice.stt",
        version="0.1.0",
        description="Speech-to-text via API endpoints",
        category=ToolCategory.VOICE,
        risk_tier=RiskTier.READ_ONLY,
        input_schema=JsonSchemaField(type="object", properties={}),
    ),
    ToolDefinition(
        name="voice.tts",
        version="0.1.0",
        description="Text-to-speech via API endpoints",
        category=ToolCategory.VOICE,
        risk_tier=RiskTier.READ_ONLY,
        input_schema=JsonSchemaField(type="object", properties={}),
    ),
    ToolDefinition(
        name="notify.send",
        version="0.1.0",
        description="Send a notification (log placeholder)",
        category=ToolCategory.NOTIFY,
        risk_tier=RiskTier.REVERSIBLE_WRITE,
        input_schema=JsonSchemaField(type="object", required=["target", "message"], properties={"target": JsonSchemaField(type="string"), "message": JsonSchemaField(type="string")}),
    ),
]


ExecutorFn = Callable[[dict[str, Any], dict[str, str]], Awaitable[Any]]


def create_tool_executors(
    workspace_root: str,
    screen_dir: str,
    twin: Any | None = None,
    extra: dict[str, Callable] | None = None,
) -> dict[str, Callable]:
    file = make_sandbox(workspace_root)
    terminal = make_terminal_tool(workspace_root)
    browser = make_browser_tools()
    screen = make_screen_tools(screen_dir)

    execs: dict[str, Callable] = {
        "fs.read": file["fs.read"],
        "fs.write": file["fs.write"],
        "fs.move": file["fs.move"],
        "fs.delete": file["fs.delete"],
        "fs.search": file["fs.search"],
        "terminal.exec": terminal["terminal.exec"],
        "browser.open": browser["browser.open"],
        "browser.search": browser["browser.search"],
        "browser.act": browser["browser.act"],
        "screen.capture": screen["screen.capture"],
        "screen.read": screen["screen.read"],
    }

    async def _memory_get(args, ctx):
        if twin is not None:
            val = twin.get(args["key"])
            if val is not None:
                return val
        return _memory_store.get(args["key"])

    async def _memory_set(args, ctx):
        if twin is not None:
            return twin.set(args["key"], args["value"], args.get("tags") or [])
        _memory_store[args["key"]] = {
            "value": args["value"],
            "tags": args.get("tags") or [],
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        return _memory_store[args["key"]]

    async def _voice_stt(args, ctx):
        return {"configured": False, "note": "use /api/voice/stt endpoint"}

    async def _voice_tts(args, ctx):
        return {"configured": False, "note": "use /api/voice/tts endpoint"}

    async def _notify_send(args, ctx):
        return {
            "queued": True,
            "target": args.get("target", "log"),
            "message": args.get("message", ""),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    execs.update({
        "memory.get": _memory_get,
        "memory.set": _memory_set,
        "voice.stt": _voice_stt,
        "voice.tts": _voice_tts,
        "notify.send": _notify_send,
    })
    if extra:
        execs.update(extra)
    return execs